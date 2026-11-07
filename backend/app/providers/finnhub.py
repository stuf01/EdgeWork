"""Finnhub earnings calendar provider."""

from __future__ import annotations

import os
import time
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Optional

import httpx
from dotenv import load_dotenv

from app.providers.base import (
    EarningsEvent,
    EarningsProvider,
    EarningsProviderError,
)
from app.providers.cache import EARNINGS_TTL_SECONDS, earnings_cache

_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_ENV_PATH, override=True)

DEFAULT_FINNHUB_URL = "https://finnhub.io/api/v1"
SYMBOL_FETCH_DELAY_SECONDS = 0.2


def _map_hour(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text == "bmo":
        return "before_open"
    if text == "amc":
        return "after_close"
    return "unknown"


def _parse_eps(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _parse_date(value: Any) -> Optional[date]:
    if value is None or value == "":
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


class FinnhubEarningsProvider(EarningsProvider):
    """Earnings calendar via Finnhub REST."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = DEFAULT_FINNHUB_URL,
        *,
        fetch_delay_seconds: float = SYMBOL_FETCH_DELAY_SECONDS,
    ) -> None:
        self._api_key = (api_key or os.getenv("FINNHUB_API_KEY") or "").strip()
        self._base_url = base_url.rstrip("/")
        self._fetch_delay_seconds = max(0.0, fetch_delay_seconds)
        if not self._api_key:
            raise EarningsProviderError(
                "FINNHUB_API_KEY is not set. Add it to backend/.env."
            )

    def get_earnings(
        self,
        symbol: str,
        from_date: date,
        to_date: date,
    ) -> list[EarningsEvent]:
        key = symbol.strip().upper()
        if not key:
            return []
        if from_date > to_date:
            raise EarningsProviderError("from_date must be on or before to_date")

        cache_key = (key, from_date.isoformat(), to_date.isoformat())
        cached = earnings_cache.get(cache_key)
        if cached is not None:
            return list(cached)

        params = {
            "symbol": key,
            "from": from_date.isoformat(),
            "to": to_date.isoformat(),
            "token": self._api_key,
        }
        url = f"{self._base_url}/calendar/earnings"
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(url, params=params)
        except httpx.RequestError as exc:
            raise EarningsProviderError(
                f"Network error fetching earnings for {key}"
            ) from exc

        if response.status_code == 401:
            raise EarningsProviderError(
                "Finnhub authentication failed (check FINNHUB_API_KEY)"
            )
        if response.status_code == 429:
            raise EarningsProviderError(
                "Finnhub rate limit exceeded; try again shortly"
            )
        if response.status_code >= 400:
            raise EarningsProviderError(
                f"Finnhub earnings request failed ({response.status_code})"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise EarningsProviderError(
                f"Invalid JSON from Finnhub for {key}"
            ) from exc

        events = self._parse_payload(key, payload)
        earnings_cache.set(cache_key, events, EARNINGS_TTL_SECONDS)
        return list(events)

    def get_earnings_for_symbols(
        self,
        symbols: list[str],
        from_date: date,
        to_date: date,
    ) -> dict[str, list[EarningsEvent]]:
        """Fetch sequentially with a short delay; isolate per-symbol failures."""
        out: dict[str, list[EarningsEvent]] = {}
        cleaned = [s.strip().upper() for s in symbols if s and s.strip()]
        for index, key in enumerate(cleaned):
            if index > 0 and self._fetch_delay_seconds > 0:
                time.sleep(self._fetch_delay_seconds)
            try:
                out[key] = self.get_earnings(key, from_date, to_date)
            except EarningsProviderError:
                continue
        return out

    @staticmethod
    def _parse_payload(symbol: str, payload: Any) -> list[EarningsEvent]:
        if not isinstance(payload, dict):
            return []
        rows = payload.get("earningsCalendar")
        if rows is None:
            rows = payload.get("earnings")
        if not isinstance(rows, list):
            return []

        events: list[EarningsEvent] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            event_date = _parse_date(row.get("date"))
            if event_date is None:
                continue
            row_symbol = str(row.get("symbol") or symbol).strip().upper() or symbol
            events.append(
                EarningsEvent(
                    symbol=row_symbol,
                    date=event_date,
                    time_of_day=_map_hour(row.get("hour")),
                    eps_estimate=_parse_eps(
                        row.get("epsEstimate", row.get("eps_estimate"))
                    ),
                )
            )
        events.sort(key=lambda item: item.date)
        return events
