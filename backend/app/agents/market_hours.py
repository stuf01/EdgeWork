"""US equity regular-session helpers (America/New_York)."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
OPEN = time(9, 30)
CLOSE = time(16, 0)
CYCLE_START = time(9, 35)
CYCLE_END = time(15, 45)
OPEN_BUFFER = timedelta(minutes=5)


def now_et(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(ET)
    if now.tzinfo is None:
        return now.replace(tzinfo=ET)
    return now.astimezone(ET)


def is_weekday(now: datetime | None = None) -> bool:
    return now_et(now).weekday() < 5


def is_market_open(now: datetime | None = None) -> bool:
    current = now_et(now)
    if current.weekday() >= 5:
        return False
    t = current.time()
    return OPEN <= t < CLOSE


def is_cycle_window(now: datetime | None = None) -> bool:
    """Scheduler window: Mon–Fri 9:35–15:45 ET."""
    current = now_et(now)
    if current.weekday() >= 5:
        return False
    t = current.time()
    return CYCLE_START <= t <= CYCLE_END


def within_open_buffer(now: datetime | None = None) -> bool:
    """True during the first 5 minutes after the open."""
    current = now_et(now)
    if current.weekday() >= 5:
        return False
    open_dt = current.replace(hour=9, minute=30, second=0, microsecond=0)
    return open_dt <= current < open_dt + OPEN_BUFFER
