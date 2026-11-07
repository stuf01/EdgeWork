"""Orchestrate NOVA → ORIN → VESK → LUMA for one cycle."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents import log_detail
from app.agents.events import log_event
from app.agents.luma import run_luma
from app.agents.market_hours import is_market_open, within_open_buffer
from app.agents.nova import run_nova
from app.agents.orin import run_orin
from app.agents.paper_client import PaperBroker, PaperTradingError
from app.agents.schemas import (
    CycleSummary,
    LumaInput,
    NovaInput,
    OrinInput,
    VeskCheckInput,
    VeskInput,
)
from app.agents.service import get_or_create_settings
from app.agents.vesk import run_vesk
from app.journal import realized_pnl
from app.models import Proposal, TradePlan
from app.providers.base import EarningsProvider, MarketDataProvider


def run_cycle(
    db: Session,
    provider: MarketDataProvider,
    broker: PaperBroker,
    *,
    earnings_provider: Optional[EarningsProvider] = None,
    force: bool = False,
    now: Optional[datetime] = None,
) -> CycleSummary:
    """Run one agent cycle. Skips when disabled, kill-switched, or market closed."""
    cycle_id = uuid.uuid4().hex
    settings = get_or_create_settings(db)
    timings: dict[str, int] = {}

    if settings.kill_switch:
        log_event(
            db,
            cycle_id=cycle_id,
            agent="SYSTEM",
            event_type="cycle_skipped",
            payload=log_detail.system_skipped("kill_switch"),
        )
        return CycleSummary(
            cycle_id=cycle_id, skipped=True, skip_reason="kill_switch"
        )
    if not settings.enabled and not force:
        log_event(
            db,
            cycle_id=cycle_id,
            agent="SYSTEM",
            event_type="cycle_skipped",
            payload=log_detail.system_skipped("disabled"),
        )
        return CycleSummary(
            cycle_id=cycle_id, skipped=True, skip_reason="disabled"
        )
    if not is_market_open(now) and not force:
        log_event(
            db,
            cycle_id=cycle_id,
            agent="SYSTEM",
            event_type="cycle_skipped",
            payload=log_detail.system_skipped("market_closed"),
        )
        return CycleSummary(
            cycle_id=cycle_id, skipped=True, skip_reason="market_closed"
        )

    log_event(
        db,
        cycle_id=cycle_id,
        agent="SYSTEM",
        event_type="cycle_start",
        payload=log_detail.system_start(force=force),
    )

    # --- NOVA ---
    t0 = time.perf_counter()
    nova_out = run_nova(
        db,
        provider,
        NovaInput(
            cycle_id=cycle_id,
            checklist_id=settings.checklist_id,
            min_checklist_score=settings.min_checklist_score,
        ),
        earnings_provider=earnings_provider,
    )
    timings["NOVA"] = int((time.perf_counter() - t0) * 1000)
    log_event(
        db,
        cycle_id=cycle_id,
        agent="NOVA",
        event_type="stage_complete",
        duration_ms=timings["NOVA"],
        payload=log_detail.nova_stage(
            [c.model_dump(mode="json") for c in nova_out.candidates],
            nova_out.skipped,
        ),
    )

    # --- ORIN ---
    t0 = time.perf_counter()
    orin_out = run_orin(
        provider,
        OrinInput(cycle_id=cycle_id, candidates=nova_out.candidates),
    )
    timings["ORIN"] = int((time.perf_counter() - t0) * 1000)
    log_event(
        db,
        cycle_id=cycle_id,
        agent="ORIN",
        event_type="stage_complete",
        duration_ms=timings["ORIN"],
        payload=log_detail.orin_stage(
            [s.model_dump(mode="json") for s in orin_out.scores],
        ),
    )

    # --- VESK ---
    t0 = time.perf_counter()
    account_size, buying_power = _account_context(broker)
    open_positions = len(broker.list_open_positions())
    trades_today = _trades_today(db)
    daily_pnl = _daily_paper_pnl(db)
    pending_symbols = _pending_symbols(db)
    open_symbols = set(broker.list_open_positions())
    market_open = is_market_open(now) or force
    open_buffer = within_open_buffer(now) and not force

    checks: list[VeskCheckInput] = []
    for candidate in nova_out.candidates:
        checks.append(
            VeskCheckInput(
                cycle_id=cycle_id,
                symbol=candidate.symbol,
                entry=candidate.entry,
                stop=candidate.stop,
                target=candidate.target,
                account_size=account_size,
                risk_percent=settings.risk_per_trade_percent,
                buying_power=buying_power,
                open_positions=open_positions,
                max_open_positions=settings.max_open_positions,
                trades_today=trades_today,
                max_trades_per_day=settings.max_trades_per_day,
                daily_pnl=daily_pnl,
                daily_loss_limit_percent=settings.daily_loss_limit_percent,
                has_open_or_pending=(
                    candidate.symbol in open_symbols
                    or candidate.symbol in pending_symbols
                ),
                days_until_earnings=candidate.days_until_earnings,
                market_open=market_open,
                within_open_buffer=open_buffer,
                last_price=candidate.last_price,
            )
        )
    vesk_out = run_vesk(VeskInput(cycle_id=cycle_id, checks=checks))
    timings["VESK"] = int((time.perf_counter() - t0) * 1000)
    log_event(
        db,
        cycle_id=cycle_id,
        agent="VESK",
        event_type="stage_complete",
        duration_ms=timings["VESK"],
        payload=log_detail.vesk_stage(
            [r.model_dump(mode="json") for r in vesk_out.results],
            account_size=format(account_size, "f"),
            buying_power=format(buying_power, "f"),
            open_positions=open_positions,
            trades_today=trades_today,
        ),
    )

    # --- LUMA ---
    t0 = time.perf_counter()
    luma_out = run_luma(
        LumaInput(
            cycle_id=cycle_id,
            candidates=nova_out.candidates,
            orin_scores=orin_out.scores,
            vesk_results=vesk_out.results,
            min_orin_score=settings.min_orin_score,
            min_checklist_score=settings.min_checklist_score,
        )
    )
    timings["LUMA"] = int((time.perf_counter() - t0) * 1000)
    log_event(
        db,
        cycle_id=cycle_id,
        agent="LUMA",
        event_type="stage_complete",
        duration_ms=timings["LUMA"],
        payload=log_detail.luma_stage(
            [d.model_dump(mode="json") for d in luma_out.decisions],
        ),
    )

    proposed = watched = skipped_n = vetoed = 0
    approved_vesk = sum(1 for r in vesk_out.results if r.approved)
    vetoed_vesk = sum(1 for r in vesk_out.results if not r.approved)
    ttl = timedelta(minutes=settings.proposal_ttl_minutes)
    now_utc = datetime.now(timezone.utc)

    for decision in luma_out.decisions:
        # Safety: never create pending proposal for a VESK veto.
        if decision.decision == "VETO" or decision.vesk_reasons:
            if decision.decision == "PROPOSE":
                # Defensive — should be unreachable.
                decision.decision = "VETO"
            status = "vetoed"
            vetoed += 1
        elif decision.decision == "PROPOSE":
            status = "pending"
            proposed += 1
        elif decision.decision == "WATCH":
            status = "cancelled"
            watched += 1
        else:
            status = "cancelled"
            skipped_n += 1

        if decision.decision in ("PROPOSE", "VETO"):
            proposal = Proposal(
                created_at=now_utc,
                cycle_id=cycle_id,
                symbol=decision.symbol,
                status=status,
                entry=decision.entry,
                stop=decision.stop,
                target=decision.target,
                shares=decision.shares,
                max_loss=decision.max_loss,
                orin_score=decision.orin_score,
                orin_expected_move_percent=decision.orin_expected_move_percent,
                checklist_score=decision.checklist_score,
                vesk_result=json.dumps(
                    {
                        "approved": decision.decision != "VETO",
                        "reasons": decision.vesk_reasons,
                    }
                ),
                luma_reasoning=decision.reasoning,
                expires_at=(now_utc + ttl) if status == "pending" else None,
            )
            db.add(proposal)
            db.flush()
            log_event(
                db,
                cycle_id=cycle_id,
                agent="LUMA",
                event_type="decision",
                symbol=decision.symbol,
                proposal_id=proposal.id,
                payload=log_detail.luma_decision(decision.model_dump(mode="json")),
                commit=False,
            )
        else:
            log_event(
                db,
                cycle_id=cycle_id,
                agent="LUMA",
                event_type="decision",
                symbol=decision.symbol,
                payload=log_detail.luma_decision(decision.model_dump(mode="json")),
                commit=False,
            )

    db.commit()
    log_event(
        db,
        cycle_id=cycle_id,
        agent="SYSTEM",
        event_type="cycle_complete",
        payload=log_detail.system_complete(
            timings,
            proposed=proposed,
            vetoed=vetoed,
        ),
    )
    return CycleSummary(
        cycle_id=cycle_id,
        skipped=False,
        nova_candidates=len(nova_out.candidates),
        orin_scores=len(orin_out.scores),
        vesk_approved=approved_vesk,
        vesk_vetoed=vetoed_vesk,
        proposed=proposed,
        watched=watched,
        skipped_decisions=skipped_n,
        stage_timings_ms=timings,
    )


def _account_context(broker: PaperBroker) -> tuple[Decimal, Decimal]:
    try:
        account = broker.get_account()
        return account.equity, account.buying_power
    except PaperTradingError:
        return Decimal("10000"), Decimal("10000")


def _trades_today(db: Session) -> int:
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    count = db.scalar(
        select(func.count())
        .select_from(TradePlan)
        .where(
            TradePlan.is_paper.is_(True),
            TradePlan.setup_tag == "agent-loop",
            TradePlan.opened_at >= start,
        )
    )
    return int(count or 0)


def _daily_paper_pnl(db: Session) -> Decimal:
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    plans = list(
        db.scalars(
            select(TradePlan).where(
                TradePlan.is_paper.is_(True),
                TradePlan.setup_tag == "agent-loop",
                TradePlan.closed_at >= start,
                TradePlan.status == "closed",
            )
        )
    )
    total = Decimal("0")
    for plan in plans:
        if plan.actual_entry is None or plan.actual_exit is None or not plan.shares_traded:
            continue
        total += realized_pnl(plan.actual_entry, plan.actual_exit, plan.shares_traded)
    return total


def _pending_symbols(db: Session) -> set[str]:
    rows = db.scalars(
        select(Proposal.symbol).where(Proposal.status.in_(("pending", "approved")))
    ).all()
    return {str(s).upper() for s in rows}
