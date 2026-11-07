"""Market data and earnings provider package."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

from app.providers.alpaca import AlpacaMarketDataProvider
from app.providers.base import EarningsProvider, MarketDataProvider
from app.providers.finnhub import FinnhubEarningsProvider
from app.providers.null_earnings import EmptyEarningsProvider

_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_ENV_PATH, override=True)


@lru_cache(maxsize=1)
def get_provider() -> MarketDataProvider:
    """Return the configured market data provider (cached singleton)."""
    return AlpacaMarketDataProvider()


@lru_cache(maxsize=1)
def get_earnings_provider() -> EarningsProvider:
    """Return Finnhub when configured; otherwise an empty provider."""
    key = (os.getenv("FINNHUB_API_KEY") or "").strip()
    if not key or key.startswith("your_"):
        return EmptyEarningsProvider()
    return FinnhubEarningsProvider(api_key=key)
