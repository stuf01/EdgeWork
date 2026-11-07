"""ORIN — Forecaster (rule/statistical score; no ML)."""

from __future__ import annotations

from decimal import Decimal

from app.agents.schemas import NovaCandidate, OrinInput, OrinOutput, OrinScore
from app.levels import sma
from app.providers.base import Bar, MarketDataError, MarketDataProvider
from app.scanner import gap_percent, relative_volume

ZERO = Decimal("0")
HUNDRED = Decimal("100")


def run_orin(provider: MarketDataProvider, body: OrinInput) -> OrinOutput:
    """Score each candidate 0–100 and estimate expected rest-of-day move %."""
    scores: list[OrinScore] = []
    for candidate in body.candidates:
        scores.append(_score_one(provider, candidate))
    return OrinOutput(scores=scores)


def _score_one(provider: MarketDataProvider, candidate: NovaCandidate) -> OrinScore:
    symbol = candidate.symbol
    try:
        bars = provider.get_daily_bars(symbol, days=520)  # ~2 years
    except MarketDataError:
        bars = []

    gap = candidate.gap_percent or ZERO
    rvol = candidate.relative_volume or ZERO
    samples, avg_move = _similar_gap_moves(bars, gap, rvol)

    factor_score = _factor_blend(candidate, bars)
    hist_score = _history_score(samples, avg_move)
    score = int(round(0.55 * factor_score + 0.45 * hist_score))
    score = max(0, min(100, score))

    expected = avg_move if samples else gap * Decimal("0.35")
    return OrinScore(
        symbol=symbol,
        score=score,
        expected_move_percent=expected.quantize(Decimal("0.01")),
        sample_count=samples,
        low_confidence=samples < 20,
        factors={
            "gap_percent": format(gap, "f"),
            "relative_volume": format(rvol, "f"),
            "has_recent_news": candidate.has_recent_news,
            "factor_score": factor_score,
            "history_score": hist_score,
        },
    )


def _similar_gap_moves(
    bars: list[Bar],
    gap: Decimal,
    rvol: Decimal,
) -> tuple[int, Decimal]:
    if len(bars) < 25:
        return 0, ZERO
    moves: list[Decimal] = []
    for i in range(21, len(bars)):
        today = bars[i]
        prev = bars[i - 1]
        day_gap = gap_percent(today.open, prev.close)
        if day_gap is None:
            continue
        # Relative volume proxy using prior day vs earlier average.
        window = bars[i - 21:i - 1]
        if len(window) < 20:
            continue
        avg_vol = sum((b.volume for b in window), 0) / Decimal(20)
        day_rvol = relative_volume(prev.volume, avg_vol)
        if day_rvol is None:
            continue
        if abs(day_gap - gap) > Decimal("2"):
            continue
        if abs(day_rvol - rvol) > Decimal("1.5"):
            continue
        # Rest-of-day move from open to close.
        if today.open == 0:
            continue
        move = (today.close - today.open) / today.open * HUNDRED
        moves.append(move)
    if not moves:
        return 0, ZERO
    avg = sum(moves, ZERO) / Decimal(len(moves))
    return len(moves), avg


def _factor_blend(candidate: NovaCandidate, bars: list[Bar]) -> float:
    score = 40.0
    gap = candidate.gap_percent or ZERO
    rvol = candidate.relative_volume or ZERO
    if gap >= Decimal("2"):
        score += 15
    if gap >= Decimal("4"):
        score += 10
    if rvol >= Decimal("1.5"):
        score += 10
    if rvol >= Decimal("2"):
        score += 10
    if candidate.has_recent_news:
        score += 5
    completed = bars[:-1] if bars else []
    sma20 = sma(completed, 20)
    sma50 = sma(completed, 50)
    entry = candidate.entry
    if sma20 is not None and entry > sma20:
        score += 5
    if sma50 is not None and entry > sma50:
        score += 5
    return max(0.0, min(100.0, score))


def _history_score(samples: int, avg_move: Decimal) -> float:
    if samples == 0:
        return 35.0
    base = 40.0 + min(30.0, samples * 1.0)
    if avg_move > 0:
        base += min(20.0, float(avg_move) * 2)
    else:
        base -= min(20.0, abs(float(avg_move)) * 2)
    return max(0.0, min(100.0, base))
