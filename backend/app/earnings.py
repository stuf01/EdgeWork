"""Pure earnings calendar helpers (no I/O)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal, Optional, Sequence

from app.providers.base import EarningsEvent

RiskLevel = Literal["today_or_tomorrow", "this_week", "later", "none"]

# Checklist rule: treat "no earnings in this window" as safely far away.
DAYS_TO_EARNINGS_SAFE_WINDOW = 60
DAYS_TO_EARNINGS_FAR = 999


def next_earnings(
    events: Sequence[EarningsEvent],
    today: date,
) -> Optional[EarningsEvent]:
    """Return the soonest earnings on or after ``today``, or None."""
    upcoming = [event for event in events if event.date >= today]
    if not upcoming:
        return None
    return min(upcoming, key=lambda event: (event.date, event.symbol))


def days_until(event: EarningsEvent, today: date) -> int:
    """Calendar days from ``today`` until the event date (may be negative)."""
    return (event.date - today).days


def risk_level(
    event: Optional[EarningsEvent],
    today: date,
) -> RiskLevel:
    """Classify proximity risk for an upcoming earnings event."""
    if event is None:
        return "none"
    days = days_until(event, today)
    if days < 0:
        return "none"
    if days <= 1:
        return "today_or_tomorrow"
    if days <= 7:
        return "this_week"
    return "later"


def days_to_earnings_for_checklist(
    events: Sequence[EarningsEvent],
    today: date,
) -> int:
    """Value for the ``days_to_earnings`` checklist rule.

    No earnings within 60 days → far-away sentinel so ``>= threshold`` passes.
    """
    upcoming = next_earnings(events, today)
    if upcoming is None:
        return DAYS_TO_EARNINGS_FAR
    days = days_until(upcoming, today)
    if days > DAYS_TO_EARNINGS_SAFE_WINDOW:
        return DAYS_TO_EARNINGS_FAR
    return days


def is_within_earnings_window(
    trade_date: date,
    earnings_dates: Sequence[date],
    skip_days: int,
) -> bool:
    """True if ``trade_date`` falls within ``skip_days`` of any earnings date."""
    if skip_days <= 0 or not earnings_dates:
        return False
    for earnings_date in earnings_dates:
        delta = abs((trade_date - earnings_date).days)
        if delta <= skip_days:
            return True
    return False


def default_earnings_lookahead(today: date, days: int = 90) -> tuple[date, date]:
    """Default from/to window for upcoming earnings lookups."""
    return today, today + timedelta(days=days)
