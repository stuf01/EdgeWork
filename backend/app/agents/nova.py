"""NOVA — Scanner agent (watchlist + checklist; no scoring/sizing)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.schemas import NovaCandidate, NovaInput, NovaOutput
from app.checklist import ChecklistRuleSpec, evaluate, score
from app.checklist_context import build_checklist_context
from app.levels import key_levels, vwap
from app.models import Checklist, WatchlistItem
from app.providers.base import (
    EarningsProvider,
    MarketDataError,
    MarketDataProvider,
)
from app.scanner import avg_daily_volume, gap_percent, relative_volume

CENT = Decimal("0.01")
TWO = Decimal("2")


def run_nova(
    db: Session,
    provider: MarketDataProvider,
    body: NovaInput,
    *,
    earnings_provider: Optional[EarningsProvider] = None,
) -> NovaOutput:
    """Return candidates that pass required checklist rules with derived levels."""
    checklist = _resolve_checklist(db, body.checklist_id)
    if checklist is None:
        return NovaOutput(candidates=[], skipped=[{"reason": "No checklist configured"}])

    symbols = list(
        db.scalars(select(WatchlistItem.symbol).order_by(WatchlistItem.added_at.desc()))
    )
    if not symbols:
        return NovaOutput(
            candidates=[],
            skipped=[{"reason": "Watchlist is empty"}],
        )

    specs = [
        ChecklistRuleSpec(
            label=rule.label,
            rule_type=rule.rule_type,
            operator=rule.operator,
            threshold=rule.threshold,
            required=rule.required,
        )
        for rule in sorted(checklist.rules, key=lambda r: r.position)
    ]

    candidates: list[NovaCandidate] = []
    skipped: list[dict[str, Any]] = []
    today = datetime.now(timezone.utc).date()

    for symbol in symbols:
        symbol = str(symbol).strip().upper()
        try:
            levels = _derive_levels(provider, symbol, today)
            if levels is None:
                skipped.append({"symbol": symbol, "reason": "Could not derive levels"})
                continue
            entry, stop, target, meta = levels
            context = build_checklist_context(
                provider,
                symbol=symbol,
                entry=entry,
                stop=stop,
                target=target,
                earnings_provider=earnings_provider,
            )
            results = evaluate(specs, context)
            scored = score(results)
            if scored.required_failed:
                skipped.append(
                    {
                        "symbol": symbol,
                        "reason": "Required checklist rules failed",
                        "required_failed": scored.required_failed,
                        "score": scored.score,
                    }
                )
                continue
            if scored.score < body.min_checklist_score:
                skipped.append(
                    {
                        "symbol": symbol,
                        "reason": "Checklist score below minimum",
                        "score": scored.score,
                    }
                )
                continue
            candidates.append(
                NovaCandidate(
                    symbol=symbol,
                    entry=entry,
                    stop=stop,
                    target=target,
                    checklist_score=scored.score,
                    gap_percent=context.get("gap_percent"),
                    relative_volume=context.get("relative_volume"),
                    last_price=context.get("last_price"),
                    has_recent_news=context.get("has_recent_news"),
                    days_until_earnings=(
                        int(context["days_to_earnings"])
                        if context.get("days_to_earnings") is not None
                        and int(context["days_to_earnings"]) < 900
                        else None
                    ),
                    context={
                        "checklist_id": checklist.id,
                        "verdict": scored.verdict,
                        **{k: meta.get(k) for k in ("prev_day_high", "prev_day_low", "vwap")},
                    },
                )
            )
        except (MarketDataError, ValueError) as exc:
            skipped.append({"symbol": symbol, "reason": str(exc)})
        except Exception as exc:  # noqa: BLE001 — isolate per symbol
            skipped.append({"symbol": symbol, "reason": f"Unexpected error: {exc}"})

    return NovaOutput(candidates=candidates, skipped=skipped)


def _resolve_checklist(db: Session, checklist_id: Optional[int]) -> Optional[Checklist]:
    if checklist_id is not None:
        return db.get(Checklist, checklist_id)
    row = db.scalars(
        select(Checklist).where(Checklist.name == "Breakout basics")
    ).first()
    if row is not None:
        return row
    return db.scalars(select(Checklist).order_by(Checklist.id.asc())).first()


def _derive_levels(
    provider: MarketDataProvider,
    symbol: str,
    today,
) -> Optional[tuple[Decimal, Decimal, Decimal, dict[str, Any]]]:
    """Entry just above PDH; stop closer of VWAP/PDL below entry; target 2R."""
    try:
        snapshots = provider.get_snapshots([symbol])
        snapshot = snapshots.get(symbol)
        daily = provider.get_daily_bars(symbol, days=60)
        intraday = provider.get_bars(symbol, timeframe="5Min")
    except MarketDataError:
        return None
    if snapshot is None:
        return None

    levels = key_levels(daily, snapshot.today_open, exclude_date=today)
    if levels.prev_day_high is None:
        return None

    entry = levels.prev_day_high + CENT
    vwap_series = vwap(intraday)
    vwap_last = vwap_series[-1] if vwap_series else None

    stop_candidates: list[Decimal] = []
    if levels.prev_day_low is not None and levels.prev_day_low < entry:
        stop_candidates.append(levels.prev_day_low)
    if vwap_last is not None and vwap_last < entry:
        stop_candidates.append(vwap_last)
    if not stop_candidates:
        # Fall back to a small percentage stop under entry.
        stop = entry * Decimal("0.98")
    else:
        # Closer to entry while still below it.
        stop = max(stop_candidates)

    if stop >= entry:
        return None
    risk = entry - stop
    target = entry + TWO * risk
    meta = {
        "prev_day_high": format(levels.prev_day_high, "f"),
        "prev_day_low": (
            format(levels.prev_day_low, "f") if levels.prev_day_low is not None else None
        ),
        "vwap": format(vwap_last, "f") if vwap_last is not None else None,
        "gap_percent": gap_percent(snapshot.today_open, snapshot.prev_close),
        "avg_daily_volume": avg_daily_volume(daily, exclude_date=today, lookback=20),
        "relative_volume": relative_volume(
            snapshot.today_volume,
            avg_daily_volume(daily, exclude_date=today, lookback=20),
        ),
    }
    return entry, stop, target, meta
