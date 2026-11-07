"""Market data provider package."""

from __future__ import annotations

from functools import lru_cache

from app.providers.alpaca import AlpacaMarketDataProvider
from app.providers.base import MarketDataProvider


@lru_cache(maxsize=1)
def get_provider() -> MarketDataProvider:
    """Return the configured market data provider (cached singleton)."""
    return AlpacaMarketDataProvider()
