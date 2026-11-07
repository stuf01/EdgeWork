"""Abstract market data provider interface and shared dataclasses."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date as DateType
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class Snapshot:
    """Latest quote-style snapshot for a symbol."""

    symbol: str
    last_price: Decimal
    today_open: Decimal
    today_volume: int
    prev_close: Decimal
    timestamp: datetime


@dataclass(frozen=True)
class Bar:
    """One daily OHLCV bar."""

    date: DateType
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


@dataclass(frozen=True)
class IntradayBar:
    """One intraday OHLCV bar with a UTC timestamp."""

    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


@dataclass(frozen=True)
class NewsItem:
    """Headline-level market news (no article body or images)."""

    id: str
    headline: str
    summary: str
    source: str
    url: str
    created_at: datetime
    symbols: tuple[str, ...]


class MarketDataError(Exception):
    """Raised when market data cannot be fetched or parsed cleanly."""


class MarketDataProvider(ABC):
    """Swap-friendly interface for market data sources."""

    @abstractmethod
    def get_snapshots(self, symbols: list[str]) -> dict[str, Snapshot]:
        """Return snapshots keyed by uppercase symbol.

        Missing symbols are omitted (not present in the dict). Provider-level
        failures (auth, rate limit, network) raise MarketDataError.
        """

    @abstractmethod
    def get_daily_bars(self, symbol: str, days: int) -> list[Bar]:
        """Return up to ``days`` most recent daily bars, oldest first."""

    @abstractmethod
    def get_bars(
        self,
        symbol: str,
        timeframe: str = "5Min",
        days: int | None = None,
    ) -> list[IntradayBar]:
        """Return OHLCV bars for a timeframe, oldest-first (UTC timestamps).

        Supports 1Min, 5Min, 15Min, 1Hour, and 1Day. When ``days`` is omitted,
        a sensible default lookback for the timeframe is used.
        """

    @abstractmethod
    def get_news(self, symbol: str, limit: int = 10) -> list[NewsItem]:
        """Return recent news for a symbol, newest first."""

    def get_news_for_symbols(
        self,
        symbols: list[str],
        limit: int = 10,
    ) -> dict[str, list[NewsItem]]:
        """Fetch news for many symbols. Default: one call per symbol.

        Providers may override to batch HTTP requests.
        """
        out: dict[str, list[NewsItem]] = {}
        for symbol in symbols:
            key = symbol.strip().upper()
            if not key:
                continue
            out[key] = self.get_news(key, limit=limit)
        return out
