"""Unit tests for scanner pure math helpers."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.providers.base import Bar
from app.scanner import avg_daily_volume, gap_percent, relative_volume


def _bar(day: date, volume: int) -> Bar:
    return Bar(
        date=day,
        open=Decimal("10"),
        high=Decimal("11"),
        low=Decimal("9"),
        close=Decimal("10.5"),
        volume=volume,
    )


def test_gap_percent_positive() -> None:
    assert gap_percent(Decimal("42"), Decimal("40")) == Decimal("5")


def test_gap_percent_negative() -> None:
    assert gap_percent(Decimal("38"), Decimal("40")) == Decimal("-5")


def test_gap_percent_missing_or_zero_prev_close() -> None:
    assert gap_percent(None, Decimal("40")) is None
    assert gap_percent(Decimal("42"), None) is None
    assert gap_percent(Decimal("42"), Decimal("0")) is None


def test_avg_daily_volume_excludes_today_and_looks_back_20() -> None:
    today = date(2026, 10, 30)
    bars = [_bar(date(2026, 10, day), 1000 + day) for day in range(1, 31)]
    # volumes for days 1..30; exclude today (30); last 20 of remaining = days 10..29
    expected_days = list(range(10, 30))
    expected = Decimal(sum(1000 + d for d in expected_days)) / Decimal(20)
    assert avg_daily_volume(bars, exclude_date=today, lookback=20) == expected


def test_avg_daily_volume_empty() -> None:
    assert avg_daily_volume([], exclude_date=date(2026, 10, 30)) is None


def test_avg_daily_volume_all_excluded() -> None:
    today = date(2026, 10, 30)
    assert avg_daily_volume([_bar(today, 5000)], exclude_date=today) is None


def test_relative_volume() -> None:
    assert relative_volume(3000, Decimal("1500")) == Decimal("2")


def test_relative_volume_divide_by_zero_and_missing() -> None:
    assert relative_volume(1000, Decimal("0")) is None
    assert relative_volume(1000, None) is None
    assert relative_volume(None, Decimal("1000")) is None
