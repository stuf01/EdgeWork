"""Pure price-level helpers (no I/O)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional, Sequence
from zoneinfo import ZoneInfo

from app.providers.base import Bar, IntradayBar

NY_TZ = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class KeyLevels:
    """Previous-day range/close plus today's open."""

    prev_day_high: Optional[Decimal]
    prev_day_low: Optional[Decimal]
    prev_day_close: Optional[Decimal]
    today_open: Optional[Decimal]


def vwap(bars: Sequence[IntradayBar]) -> list[Decimal]:
    """Cumulative VWAP with a reset on each America/New_York trading day.

    typical_price = (high + low + close) / 3
    VWAP = cumulative(typical_price * volume) / cumulative(volume)

    Returns one VWAP value per input bar (bars should already be sorted).
    """
    if not bars:
        return []

    ordered = sorted(bars, key=lambda bar: bar.timestamp)
    cumulative_pv = Decimal("0")
    cumulative_vol = Decimal("0")
    current_day: Optional[date] = None
    series: list[Decimal] = []

    for bar in ordered:
        day = bar.timestamp.astimezone(NY_TZ).date()
        if current_day != day:
            current_day = day
            cumulative_pv = Decimal("0")
            cumulative_vol = Decimal("0")

        typical = (bar.high + bar.low + bar.close) / Decimal("3")
        if bar.volume > 0:
            cumulative_pv += typical * Decimal(bar.volume)
            cumulative_vol += Decimal(bar.volume)
        if cumulative_vol > 0:
            series.append(cumulative_pv / cumulative_vol)
        else:
            series.append(typical)
    return series


def key_levels(
    daily_bars: Sequence[Bar],
    today_open: Optional[Decimal],
    *,
    exclude_date: Optional[date] = None,
) -> KeyLevels:
    """Previous completed daily bar high/low/close plus provided today open."""
    completed = [
        bar
        for bar in daily_bars
        if exclude_date is None or bar.date != exclude_date
    ]
    if not completed:
        return KeyLevels(
            prev_day_high=None,
            prev_day_low=None,
            prev_day_close=None,
            today_open=today_open,
        )
    prev = completed[-1]
    return KeyLevels(
        prev_day_high=prev.high,
        prev_day_low=prev.low,
        prev_day_close=prev.close,
        today_open=today_open,
    )


def sma(daily_bars: Sequence[Bar], period: int) -> Optional[Decimal]:
    """Simple moving average of closes over ``period`` bars."""
    if period <= 0:
        return None
    if len(daily_bars) < period:
        return None
    window = daily_bars[-period:]
    total = sum((bar.close for bar in window), start=Decimal("0"))
    return total / Decimal(period)
