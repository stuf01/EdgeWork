"""Unit tests for earnings helpers."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.earnings import (
    DAYS_TO_EARNINGS_FAR,
    days_to_earnings_for_checklist,
    days_until,
    is_within_earnings_window,
    next_earnings,
    risk_level,
)
from app.providers.base import EarningsEvent


def _event(day: date, tod: str = "after_close") -> EarningsEvent:
    return EarningsEvent(
        symbol="TEST",
        date=day,
        time_of_day=tod,
        eps_estimate=Decimal("1.00"),
    )


def test_next_earnings_today_and_tomorrow() -> None:
    today = date(2026, 11, 6)
    events = [
        _event(today - timedelta(days=1)),
        _event(today),
        _event(today + timedelta(days=5)),
    ]
    upcoming = next_earnings(events, today)
    assert upcoming is not None
    assert upcoming.date == today
    assert days_until(upcoming, today) == 0
    assert risk_level(upcoming, today) == "today_or_tomorrow"

    tomorrow = _event(today + timedelta(days=1))
    assert days_until(tomorrow, today) == 1
    assert risk_level(tomorrow, today) == "today_or_tomorrow"


def test_next_earnings_ignores_past_and_empty() -> None:
    today = date(2026, 11, 6)
    assert next_earnings([], today) is None
    assert risk_level(None, today) == "none"

    past_only = [_event(today - timedelta(days=3))]
    assert next_earnings(past_only, today) is None
    assert risk_level(next_earnings(past_only, today), today) == "none"


def test_risk_level_this_week_and_later() -> None:
    today = date(2026, 11, 6)
    week = _event(today + timedelta(days=5))
    later = _event(today + timedelta(days=20))
    assert risk_level(week, today) == "this_week"
    assert risk_level(later, today) == "later"


def test_days_to_earnings_for_checklist() -> None:
    today = date(2026, 11, 6)
    assert days_to_earnings_for_checklist([], today) == DAYS_TO_EARNINGS_FAR
    near = [_event(today + timedelta(days=1))]
    assert days_to_earnings_for_checklist(near, today) == 1
    far = [_event(today + timedelta(days=90))]
    assert days_to_earnings_for_checklist(far, today) == DAYS_TO_EARNINGS_FAR


def test_is_within_earnings_window() -> None:
    day = date(2026, 6, 15)
    earnings = [date(2026, 6, 17)]
    assert is_within_earnings_window(day, earnings, 2) is True
    assert is_within_earnings_window(day, earnings, 1) is False
    assert is_within_earnings_window(day, earnings, 0) is False
