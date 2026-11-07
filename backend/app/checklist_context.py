"""Build checklist evaluation context from market data (I/O allowed)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

from app.earnings import days_to_earnings_for_checklist
from app.levels import key_levels, sma, vwap
from app.news import news_activity
from app.planner import calculate_plan
from app.providers import get_earnings_provider
from app.providers.base import (
    EarningsProvider,
    EarningsProviderError,
    MarketDataError,
    MarketDataProvider,
)
from app.scanner import avg_daily_volume, gap_percent, relative_volume


def build_checklist_context(
    provider: MarketDataProvider,
    *,
    symbol: str,
    entry: Decimal,
    stop: Decimal,
    target: Decimal,
    earnings_provider: Optional[EarningsProvider] = None,
) -> dict[str, Any]:
    """Gather market + plan metrics; missing pieces stay absent (None)."""
    symbol = symbol.strip().upper()
    context: dict[str, Any] = {
        "symbol": symbol,
        "entry": entry,
        "stop": stop,
        "target": target,
    }

    try:
        plan = calculate_plan(
            Decimal("10000"),
            Decimal("1"),
            entry,
            stop,
            target,
        )
        context["risk_reward"] = plan["risk_reward_ratio"]
    except ValueError:
        context["risk_reward"] = None

    if entry > 0 and stop > 0 and entry > stop:
        context["stop_distance_percent"] = (entry - stop) / entry * Decimal("100")
    else:
        context["stop_distance_percent"] = None

    # spread_percent is optional — leave unset so rules become unknown
    context["spread_percent"] = None

    try:
        snapshots = provider.get_snapshots([symbol])
        snapshot = snapshots.get(symbol)
    except MarketDataError:
        snapshot = None

    last_price: Optional[Decimal] = None
    if snapshot is not None:
        last_price = snapshot.last_price
        context["last_price"] = last_price
        context["gap_percent"] = gap_percent(snapshot.today_open, snapshot.prev_close)
        try:
            bars = provider.get_daily_bars(symbol, days=60)
        except MarketDataError:
            bars = []
        today = datetime.now(timezone.utc).date()
        avg_vol = avg_daily_volume(bars, exclude_date=today, lookback=20)
        context["avg_daily_volume"] = avg_vol
        context["relative_volume"] = relative_volume(snapshot.today_volume, avg_vol)
        levels = key_levels(
            bars,
            snapshot.today_open,
            exclude_date=today,
        )
        if last_price is not None and levels.prev_day_high is not None:
            context["price_above_prev_day_high"] = (
                last_price > levels.prev_day_high
            )
        else:
            context["price_above_prev_day_high"] = None
        if last_price is not None and levels.prev_day_low is not None:
            context["price_above_prev_day_low"] = last_price > levels.prev_day_low
        else:
            context["price_above_prev_day_low"] = None
        completed = [bar for bar in bars if bar.date != today]
        sma20 = sma(completed, 20)
        sma50 = sma(completed, 50)
        context["entry_above_sma_20"] = (
            entry > sma20 if sma20 is not None else None
        )
        context["entry_above_sma_50"] = (
            entry > sma50 if sma50 is not None else None
        )
    else:
        context["last_price"] = None
        context["gap_percent"] = None
        context["avg_daily_volume"] = None
        context["relative_volume"] = None
        context["price_above_prev_day_high"] = None
        context["price_above_prev_day_low"] = None
        context["entry_above_sma_20"] = None
        context["entry_above_sma_50"] = None

    try:
        intraday = provider.get_bars(symbol, timeframe="5Min")
        vwap_series = vwap(intraday)
        if last_price is not None and vwap_series:
            context["price_above_vwap"] = last_price > vwap_series[-1]
        else:
            context["price_above_vwap"] = None
    except MarketDataError:
        context["price_above_vwap"] = None

    try:
        news_items = provider.get_news(symbol, limit=20)
        _, has_recent = news_activity(news_items)
        context["has_recent_news"] = has_recent
    except MarketDataError:
        context["has_recent_news"] = None

    today = datetime.now(timezone.utc).date()
    try:
        earn_provider = earnings_provider or get_earnings_provider()
        events = earn_provider.get_earnings(
            symbol,
            today,
            today + timedelta(days=90),
        )
        context["days_to_earnings"] = Decimal(
            days_to_earnings_for_checklist(events, today)
        )
    except EarningsProviderError:
        context["days_to_earnings"] = None
    except Exception:  # noqa: BLE001 — optional enrichment
        context["days_to_earnings"] = None

    return context
