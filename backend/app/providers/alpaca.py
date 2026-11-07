"""Alpaca market data provider (IEX feed via REST + httpx)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Optional

import httpx
from dotenv import load_dotenv

from app.providers.base import (
    Bar,
    IntradayBar,
    MarketDataError,
    MarketDataProvider,
    NewsItem,
    Snapshot,
)
from app.providers.cache import (
    BARS_TTL_SECONDS,
    DAILY_CHART_TTL_SECONDS,
    INTRADAY_TTL_SECONDS,
    NEWS_TTL_SECONDS,
    SNAPSHOT_TTL_SECONDS,
    bars_cache,
    chart_bars_cache,
    news_cache,
    snapshot_cache,
)
from app.timeframes import ALLOWED_TIMEFRAMES, DEFAULT_TIMEFRAME

_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_ENV_PATH, override=True)

DEFAULT_DATA_URL = "https://data.alpaca.markets"
SNAPSHOT_BATCH_SIZE = 50


def _normalize_data_url(url: str) -> str:
    """Coerce common misconfigured trading-API URLs to the data API host."""
    cleaned = url.strip().rstrip("/")
    if not cleaned:
        return DEFAULT_DATA_URL
    lower = cleaned.lower()
    # Trading hosts are not valid for market-data snapshots/bars.
    if "paper-api.alpaca.markets" in lower or lower.startswith(
        "https://api.alpaca.markets"
    ):
        return DEFAULT_DATA_URL
    if cleaned.endswith("/v2"):
        cleaned = cleaned[:-3]
    return cleaned


def _to_decimal(value: Any, field: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise MarketDataError(f"Invalid numeric value for {field}: {value!r}") from exc


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise MarketDataError(f"Invalid timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


class AlpacaMarketDataProvider(MarketDataProvider):
    """Market data via Alpaca's free IEX REST feed."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        data_url: Optional[str] = None,
        timeout: float = 20.0,
    ) -> None:
        self.api_key = api_key or os.getenv("ALPACA_API_KEY", "").strip()
        self.api_secret = api_secret or os.getenv("ALPACA_API_SECRET", "").strip()
        self.data_url = _normalize_data_url(
            data_url or os.getenv("ALPACA_DATA_URL", DEFAULT_DATA_URL)
        )
        self.timeout = timeout
        if not self.api_key or not self.api_secret:
            raise MarketDataError(
                "Alpaca credentials missing. Set ALPACA_API_KEY and "
                "ALPACA_API_SECRET in backend/.env"
            )

    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.api_secret,
        }

    def _request(self, method: str, path: str, params: dict[str, Any]) -> Any:
        url = f"{self.data_url}{path}"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.request(
                    method,
                    url,
                    params=params,
                    headers=self._headers(),
                )
        except httpx.HTTPError as exc:
            raise MarketDataError(f"Alpaca network error: {exc}") from exc

        if response.status_code == 429:
            raise MarketDataError(
                "Alpaca rate limit exceeded (429). Wait a moment and try again."
            )
        if response.status_code in (401, 403):
            raise MarketDataError(
                "Alpaca authentication failed. Check ALPACA_API_KEY / "
                "ALPACA_API_SECRET."
            )
        if response.status_code >= 400:
            detail = response.text.strip() or response.reason_phrase
            raise MarketDataError(
                f"Alpaca HTTP {response.status_code}: {detail}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise MarketDataError("Alpaca returned non-JSON response") from exc

    def get_snapshots(self, symbols: list[str]) -> dict[str, Snapshot]:
        cleaned = sorted({s.strip().upper() for s in symbols if s and s.strip()})
        if not cleaned:
            return {}

        result: dict[str, Snapshot] = {}
        missing: list[str] = []
        for symbol in cleaned:
            cached = snapshot_cache.get(symbol)
            if cached is not None:
                result[symbol] = cached
            else:
                missing.append(symbol)

        for i in range(0, len(missing), SNAPSHOT_BATCH_SIZE):
            batch = missing[i:i + SNAPSHOT_BATCH_SIZE]
            payload = self._request(
                "GET",
                "/v2/stocks/snapshots",
                {"symbols": ",".join(batch), "feed": "iex"},
            )
            if not isinstance(payload, dict):
                raise MarketDataError("Unexpected Alpaca snapshots payload")

            for symbol in batch:
                raw = payload.get(symbol)
                if raw is None:
                    continue
                try:
                    snapshot = self._parse_snapshot(symbol, raw)
                except MarketDataError:
                    continue
                snapshot_cache.set(symbol, snapshot, SNAPSHOT_TTL_SECONDS)
                result[symbol] = snapshot

        return result

    def get_daily_bars(self, symbol: str, days: int) -> list[Bar]:
        symbol = symbol.strip().upper()
        if not symbol:
            raise MarketDataError("Symbol is required for daily bars")
        if days <= 0:
            return []

        cache_key = (symbol, days)
        cached = bars_cache.get(cache_key)
        if cached is not None:
            return cached

        # Request extra calendar days to cover weekends/holidays.
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=max(days * 3, days + 10))
        params: dict[str, Any] = {
            "timeframe": "1Day",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "adjustment": "raw",
            "feed": "iex",
            "limit": min(max(days + 5, days), 10000),
            "sort": "asc",
        }
        payload = self._request(
            "GET",
            f"/v2/stocks/{symbol}/bars",
            params,
        )
        raw_bars = payload.get("bars") if isinstance(payload, dict) else None
        if raw_bars is None:
            bars: list[Bar] = []
        else:
            bars = []
            for raw in raw_bars:
                try:
                    bars.append(self._parse_bar(raw))
                except MarketDataError:
                    continue
            if len(bars) > days:
                bars = bars[-days:]

        bars_cache.set(cache_key, bars, BARS_TTL_SECONDS)
        return bars

    def get_bars(
        self,
        symbol: str,
        timeframe: str = DEFAULT_TIMEFRAME,
        days: Optional[int] = None,
    ) -> list[IntradayBar]:
        symbol = symbol.strip().upper()
        if not symbol:
            raise MarketDataError("Symbol is required for bars")
        if timeframe not in ALLOWED_TIMEFRAMES:
            raise MarketDataError(f"Unsupported timeframe: {timeframe}")

        config = ALLOWED_TIMEFRAMES[timeframe]
        lookback_days = days if days is not None else config["days"]
        if lookback_days <= 0:
            return []

        cache_key = (symbol, timeframe)
        cached = chart_bars_cache.get(cache_key)
        if cached is not None:
            return cached

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=lookback_days)
        # Extra calendar padding for daily so we can still return ~1 year of
        # trading sessions after weekends/holidays.
        if timeframe == "1Day":
            start = end - timedelta(days=max(lookback_days + 40, lookback_days))

        params: dict[str, Any] = {
            "timeframe": timeframe,
            "start": start.isoformat().replace("+00:00", "Z"),
            "end": end.isoformat().replace("+00:00", "Z"),
            "adjustment": "raw",
            "feed": "iex",
            "limit": min(config["max_bars"], 10000),
            "sort": "asc",
        }
        payload = self._request(
            "GET",
            f"/v2/stocks/{symbol}/bars",
            params,
        )
        raw_bars = payload.get("bars") if isinstance(payload, dict) else None
        bars: list[IntradayBar] = []
        if raw_bars:
            for raw in raw_bars:
                try:
                    bars.append(self._parse_intraday_bar(raw))
                except MarketDataError:
                    continue
            if len(bars) > config["max_bars"]:
                bars = bars[-config["max_bars"]:]

        ttl = (
            DAILY_CHART_TTL_SECONDS
            if timeframe == "1Day"
            else INTRADAY_TTL_SECONDS
        )
        chart_bars_cache.set(cache_key, bars, ttl)
        return bars

    def get_news(self, symbol: str, limit: int = 10) -> list[NewsItem]:
        symbol = symbol.strip().upper()
        if not symbol:
            return []
        limit = max(1, min(limit, 50))
        cache_key = (symbol, limit)
        cached = news_cache.get(cache_key)
        if cached is not None:
            return cached

        items = self._fetch_news([symbol], limit=limit)
        # Keep only items that mention this symbol when present.
        filtered = [
            item
            for item in items
            if not item.symbols or symbol in item.symbols
        ]
        news_cache.set(cache_key, filtered, NEWS_TTL_SECONDS)
        return filtered

    def get_news_for_symbols(
        self,
        symbols: list[str],
        limit: int = 10,
    ) -> dict[str, list[NewsItem]]:
        cleaned = sorted({s.strip().upper() for s in symbols if s and s.strip()})
        out: dict[str, list[NewsItem]] = {symbol: [] for symbol in cleaned}
        if not cleaned:
            return out

        missing: list[str] = []
        for symbol in cleaned:
            cached = news_cache.get((symbol, limit))
            if cached is not None:
                out[symbol] = cached
            else:
                missing.append(symbol)

        if missing:
            # One batched request; then split by mentioned symbol.
            batch_limit = max(limit, min(50, limit * max(1, len(missing))))
            items = self._fetch_news(missing, limit=batch_limit)
            buckets: dict[str, list[NewsItem]] = {symbol: [] for symbol in missing}
            for item in items:
                targets = [s for s in item.symbols if s in buckets] or missing
                for symbol in targets:
                    if symbol in buckets:
                        buckets[symbol].append(item)
            for symbol, bucket in buckets.items():
                trimmed = bucket[:limit]
                news_cache.set((symbol, limit), trimmed, NEWS_TTL_SECONDS)
                out[symbol] = trimmed
        return out

    def _fetch_news(self, symbols: list[str], limit: int) -> list[NewsItem]:
        payload = self._request(
            "GET",
            "/v1beta1/news",
            {
                "symbols": ",".join(symbols),
                "limit": limit,
                "sort": "desc",
            },
        )
        raw_items = payload.get("news") if isinstance(payload, dict) else None
        if not raw_items:
            return []
        items: list[NewsItem] = []
        for raw in raw_items:
            try:
                items.append(self._parse_news_item(raw))
            except MarketDataError:
                continue
        items.sort(key=lambda item: item.created_at, reverse=True)
        return items

    def _parse_news_item(self, raw: dict[str, Any]) -> NewsItem:
        created_raw = raw.get("created_at") or raw.get("updated_at")
        if created_raw is None:
            raise MarketDataError("News item missing created_at")
        symbols_raw = raw.get("symbols") or []
        symbols = tuple(
            str(symbol).strip().upper()
            for symbol in symbols_raw
            if str(symbol).strip()
        )
        return NewsItem(
            id=str(raw.get("id", "")),
            headline=str(raw.get("headline") or "").strip(),
            summary=str(raw.get("summary") or "").strip(),
            source=str(raw.get("source") or "").strip(),
            url=str(raw.get("url") or "").strip(),
            created_at=_parse_timestamp(created_raw),
            symbols=symbols,
        )

    def _parse_snapshot(self, symbol: str, raw: dict[str, Any]) -> Snapshot:
        daily = raw.get("dailyBar") or {}
        prev = raw.get("prevDailyBar") or {}
        latest_trade = raw.get("latestTrade") or {}
        latest_quote = raw.get("latestQuote") or {}

        last_price_raw = latest_trade.get("p")
        if last_price_raw is None:
            last_price_raw = daily.get("c")
        if last_price_raw is None:
            # Mid of bid/ask as last resort
            bid = latest_quote.get("bp")
            ask = latest_quote.get("ap")
            if bid is not None and ask is not None:
                last_price_raw = (Decimal(str(bid)) + Decimal(str(ask))) / 2

        today_open_raw = daily.get("o")
        today_volume_raw = daily.get("v")
        prev_close_raw = prev.get("c")

        if (
            last_price_raw is None
            or today_open_raw is None
            or today_volume_raw is None
            or prev_close_raw is None
        ):
            raise MarketDataError(f"Incomplete snapshot for {symbol}")

        ts_raw = latest_trade.get("t") or daily.get("t")
        timestamp = (
            _parse_timestamp(ts_raw)
            if ts_raw is not None
            else datetime.now(timezone.utc)
        )

        return Snapshot(
            symbol=symbol,
            last_price=_to_decimal(last_price_raw, "last_price"),
            today_open=_to_decimal(today_open_raw, "today_open"),
            today_volume=int(today_volume_raw),
            prev_close=_to_decimal(prev_close_raw, "prev_close"),
            timestamp=timestamp,
        )

    def _parse_bar(self, raw: dict[str, Any]) -> Bar:
        ts = raw.get("t")
        if ts is None:
            raise MarketDataError("Bar missing timestamp")
        bar_date = _parse_timestamp(ts).date()
        return Bar(
            date=bar_date,
            open=_to_decimal(raw.get("o"), "open"),
            high=_to_decimal(raw.get("h"), "high"),
            low=_to_decimal(raw.get("l"), "low"),
            close=_to_decimal(raw.get("c"), "close"),
            volume=int(raw.get("v", 0)),
        )

    def _parse_intraday_bar(self, raw: dict[str, Any]) -> IntradayBar:
        ts = raw.get("t")
        if ts is None:
            raise MarketDataError("Intraday bar missing timestamp")
        return IntradayBar(
            timestamp=_parse_timestamp(ts),
            open=_to_decimal(raw.get("o"), "open"),
            high=_to_decimal(raw.get("h"), "high"),
            low=_to_decimal(raw.get("l"), "low"),
            close=_to_decimal(raw.get("c"), "close"),
            volume=int(raw.get("v", 0)),
        )
