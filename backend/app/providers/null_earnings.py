"""No-op earnings provider used when Finnhub is not configured."""

from __future__ import annotations

from datetime import date

from app.providers.base import EarningsEvent, EarningsProvider


class EmptyEarningsProvider(EarningsProvider):
    """Returns no events; used when FINNHUB_API_KEY is unset."""

    def get_earnings(
        self,
        symbol: str,
        from_date: date,
        to_date: date,
    ) -> list[EarningsEvent]:
        return []
