"""Simple in-memory TTL cache for market data responses."""

from __future__ import annotations

import time
from threading import Lock
from typing import Any, Generic, Hashable, Optional, TypeVar

T = TypeVar("T")


class TTLCache(Generic[T]):
    """Thread-safe dict cache with per-entry TTL."""

    def __init__(self) -> None:
        self._store: dict[Hashable, tuple[float, T]] = {}
        self._lock = Lock()

    def get(self, key: Hashable) -> Optional[T]:
        now = time.monotonic()
        with self._lock:
            item = self._store.get(key)
            if item is None:
                return None
            expires_at, value = item
            if now >= expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: Hashable, value: T, ttl_seconds: float) -> None:
        with self._lock:
            self._store[key] = (time.monotonic() + ttl_seconds, value)

    def delete(self, key: Hashable) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


# Shared caches used by providers
snapshot_cache: TTLCache[Any] = TTLCache()
bars_cache: TTLCache[Any] = TTLCache()
# Chart bars keyed by (symbol, timeframe)
chart_bars_cache: TTLCache[Any] = TTLCache()
news_cache: TTLCache[Any] = TTLCache()
earnings_cache: TTLCache[Any] = TTLCache()

SNAPSHOT_TTL_SECONDS = 30
BARS_TTL_SECONDS = 6 * 60 * 60
INTRADAY_TTL_SECONDS = 30
DAILY_CHART_TTL_SECONDS = 6 * 60 * 60
NEWS_TTL_SECONDS = 5 * 60
EARNINGS_TTL_SECONDS = 12 * 60 * 60
