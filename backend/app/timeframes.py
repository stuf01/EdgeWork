"""Allowed chart timeframes and lookback defaults."""

from __future__ import annotations

from typing import TypedDict


class TimeframeConfig(TypedDict):
    days: int
    max_bars: int
    intraday: bool


ALLOWED_TIMEFRAMES: dict[str, TimeframeConfig] = {
    "1Min": {"days": 2, "max_bars": 1000, "intraday": True},
    "5Min": {"days": 5, "max_bars": 800, "intraday": True},
    "15Min": {"days": 10, "max_bars": 600, "intraday": True},
    "1Hour": {"days": 30, "max_bars": 500, "intraday": True},
    "1Day": {"days": 365, "max_bars": 260, "intraday": False},
}

DEFAULT_TIMEFRAME = "5Min"


def is_valid_timeframe(timeframe: str) -> bool:
    return timeframe in ALLOWED_TIMEFRAMES


def is_intraday_timeframe(timeframe: str) -> bool:
    config = ALLOWED_TIMEFRAMES.get(timeframe)
    return bool(config and config["intraday"])
