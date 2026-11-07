"""Unit tests for VWAP, SMA, and key level helpers."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from app.levels import key_levels, sma, vwap
from app.providers.base import Bar, IntradayBar


def _intraday(
    hour: int,
    minute: int,
    *,
    high: str,
    low: str,
    close: str,
    volume: int,
    day: date = date(2026, 10, 30),
) -> IntradayBar:
    # 14:30 UTC == 10:30 America/New_York on this date (EDT, UTC-4)
    ts = datetime(day.year, day.month, day.day, hour, minute, tzinfo=timezone.utc)
    return IntradayBar(
        timestamp=ts,
        open=Decimal(low),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=volume,
    )


def _daily(day: date, high: str, low: str, close: str) -> Bar:
    return Bar(
        date=day,
        open=Decimal(close),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=1_000_000,
    )


def test_vwap_hand_calculated() -> None:
    # Both bars on 2026-10-30 America/New_York (UTC timestamps during RTH)
    bars = [
        _intraday(14, 30, high="11", low="9", close="10", volume=100),
        _intraday(14, 35, high="12", low="10", close="11", volume=100),
    ]
    # TP1 = 10, TP2 = 11 → VWAP = [10, 10.5]
    assert vwap(bars) == [Decimal("10"), Decimal("10.5")]


def test_vwap_resets_each_trading_day() -> None:
    prior = date(2026, 10, 29)
    bars = [
        _intraday(14, 30, high="20", low="20", close="20", volume=50, day=prior),
        _intraday(14, 30, high="11", low="9", close="10", volume=100),
        _intraday(14, 35, high="12", low="10", close="11", volume=100),
    ]
    # Prior day VWAP resets; second day starts fresh at 10 then 10.5
    assert vwap(bars) == [Decimal("20"), Decimal("10"), Decimal("10.5")]


def test_vwap_empty() -> None:
    assert vwap([]) == []


def test_sma_happy_path() -> None:
    bars = [
        _daily(date(2026, 10, day), "11", "9", str(day))
        for day in range(1, 6)
    ]
    # closes 1..5, period 3 → (3+4+5)/3 = 4
    assert sma(bars, 3) == Decimal("4")


def test_sma_too_few_bars_returns_none() -> None:
    bars = [_daily(date(2026, 10, 1), "11", "9", "10")]
    assert sma(bars, 20) is None
    assert sma([], 20) is None
    assert sma(bars, 0) is None


def test_key_levels() -> None:
    bars = [
        _daily(date(2026, 10, 28), "12", "8", "10"),
        _daily(date(2026, 10, 29), "15", "11", "14"),
        _daily(date(2026, 10, 30), "16", "13", "15"),
    ]
    levels = key_levels(
        bars,
        Decimal("15.5"),
        exclude_date=date(2026, 10, 30),
    )
    assert levels.prev_day_high == Decimal("15")
    assert levels.prev_day_low == Decimal("11")
    assert levels.prev_day_close == Decimal("14")
    assert levels.today_open == Decimal("15.5")


def test_key_levels_empty() -> None:
    levels = key_levels([], Decimal("10"))
    assert levels.prev_day_high is None
    assert levels.prev_day_close is None
    assert levels.today_open == Decimal("10")
