"""Pure scanner math helpers (no I/O)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional, Sequence

from app.providers.base import Bar


def gap_percent(
    today_open: Optional[Decimal],
    prev_close: Optional[Decimal],
) -> Optional[Decimal]:
    """(today_open - prev_close) / prev_close * 100, or None if unsafe."""
    if today_open is None or prev_close is None:
        return None
    if prev_close == 0:
        return None
    return (today_open - prev_close) / prev_close * Decimal("100")


def avg_daily_volume(
    bars: Sequence[Bar],
    *,
    exclude_date: Optional[date] = None,
    lookback: int = 20,
) -> Optional[Decimal]:
    """Average volume of the last ``lookback`` completed daily bars.

    Bars matching ``exclude_date`` (typically today) are excluded first.
    Returns None when there are no usable bars.
    """
    completed = [bar for bar in bars if exclude_date is None or bar.date != exclude_date]
    if not completed:
        return None
    window = completed[-lookback:]
    if not window:
        return None
    total = sum((bar.volume for bar in window), start=0)
    return Decimal(total) / Decimal(len(window))


def relative_volume(
    today_volume: Optional[int],
    avg_volume: Optional[Decimal],
) -> Optional[Decimal]:
    """today_volume / avg_daily_volume, or None if unsafe."""
    if today_volume is None or avg_volume is None:
        return None
    if avg_volume == 0:
        return None
    return Decimal(today_volume) / avg_volume
