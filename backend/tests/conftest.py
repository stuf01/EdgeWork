"""Shared pytest fixtures: in-memory SQLite and fake market data."""

from __future__ import annotations

from collections.abc import Generator
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app, get_market_data_provider
from app.models import (  # noqa: F401
    BacktestRun,
    Checklist,
    ChecklistRule,
    TradePlan,
    WatchlistItem,
)
from app.providers.base import (
    Bar,
    IntradayBar,
    MarketDataError,
    MarketDataProvider,
    NewsItem,
    Snapshot,
)
from app.providers.cache import (
    DAILY_CHART_TTL_SECONDS,
    INTRADAY_TTL_SECONDS,
    chart_bars_cache,
)
from app.timeframes import ALLOWED_TIMEFRAMES, DEFAULT_TIMEFRAME


class FakeProvider(MarketDataProvider):
    """In-memory provider used by API tests — no network."""

    def __init__(self) -> None:
        today = datetime.now(timezone.utc).date()
        self.today = today
        self._snapshots: dict[str, Snapshot] = {
            "GOOD": Snapshot(
                symbol="GOOD",
                last_price=Decimal("25.00"),
                today_open=Decimal("24.00"),
                today_volume=3_000_000,
                prev_close=Decimal("20.00"),
                timestamp=datetime.now(timezone.utc),
            ),
            "FLAT": Snapshot(
                symbol="FLAT",
                last_price=Decimal("50.00"),
                today_open=Decimal("50.10"),
                today_volume=100_000,
                prev_close=Decimal("50.00"),
                timestamp=datetime.now(timezone.utc),
            ),
            "CHEAP": Snapshot(
                symbol="CHEAP",
                last_price=Decimal("2.00"),
                today_open=Decimal("3.00"),
                today_volume=5_000_000,
                prev_close=Decimal("2.00"),
                timestamp=datetime.now(timezone.utc),
            ),
            "BAD": Snapshot(
                symbol="BAD",
                last_price=Decimal("10.00"),
                today_open=Decimal("10.00"),
                today_volume=1,
                prev_close=Decimal("10.00"),
                timestamp=datetime.now(timezone.utc),
            ),
        }
        self._bars: dict[str, list[Bar]] = {
            "GOOD": self._make_bars(today, 1_000_000),
            "FLAT": self._make_bars(today, 200_000),
            "CHEAP": self._make_bars(today, 1_000_000),
        }
        self._bar_errors: set[str] = {"BAD"}
        self._intraday: dict[str, list[IntradayBar]] = {
            "GOOD": self._make_intraday("GOOD"),
            "FLAT": self._make_intraday("FLAT"),
            "CHEAP": self._make_intraday("CHEAP"),
        }
        self.fetch_counts: dict[tuple[str, str], int] = {}
        self.news_fail = False
        self.news_by_symbol: dict[str, list[NewsItem]] = {
            "GOOD": [
                NewsItem(
                    id="1",
                    headline="GOOD pops on earnings",
                    summary="Beat estimates",
                    source="TestWire",
                    url="https://example.com/good",
                    created_at=datetime.now(timezone.utc) - timedelta(hours=2),
                    symbols=("GOOD",),
                ),
                NewsItem(
                    id="2",
                    headline="Older GOOD item",
                    summary="Prior news",
                    source="TestWire",
                    url="https://example.com/good-old",
                    created_at=datetime.now(timezone.utc) - timedelta(days=3),
                    symbols=("GOOD",),
                ),
            ],
            "FLAT": [],
        }
        chart_bars_cache.clear()

    @staticmethod
    def _make_bars(today: date, volume: int) -> list[Bar]:
        bars: list[Bar] = []
        for i in range(25, 0, -1):
            day = today - timedelta(days=i)
            bars.append(
                Bar(
                    date=day,
                    open=Decimal("10"),
                    high=Decimal("11"),
                    low=Decimal("9"),
                    close=Decimal("10"),
                    volume=volume,
                )
            )
        bars.append(
            Bar(
                date=today,
                open=Decimal("10"),
                high=Decimal("12"),
                low=Decimal("9"),
                close=Decimal("11"),
                volume=volume * 2,
            )
        )
        return bars

    @staticmethod
    def _make_intraday(symbol: str) -> list[IntradayBar]:
        base = datetime(2026, 10, 30, 14, 30, tzinfo=timezone.utc)
        price = Decimal("25") if symbol == "GOOD" else Decimal("50")
        bars: list[IntradayBar] = []
        for i in range(3):
            bars.append(
                IntradayBar(
                    timestamp=base + timedelta(minutes=5 * i),
                    open=price,
                    high=price + Decimal("1"),
                    low=price - Decimal("1"),
                    close=price,
                    volume=1000 * (i + 1),
                )
            )
        return bars

    def get_snapshots(self, symbols: list[str]) -> dict[str, Snapshot]:
        return {
            symbol.upper(): self._snapshots[symbol.upper()]
            for symbol in symbols
            if symbol.upper() in self._snapshots
        }

    def get_daily_bars(self, symbol: str, days: int) -> list[Bar]:
        key = symbol.upper()
        if key in self._bar_errors:
            raise MarketDataError(f"No bars for {key}")
        bars = self._bars.get(key, [])
        return bars[-days:] if days else []

    def get_bars(
        self,
        symbol: str,
        timeframe: str = DEFAULT_TIMEFRAME,
        days: int | None = None,
    ) -> list[IntradayBar]:
        key = symbol.upper()
        if key in self._bar_errors:
            raise MarketDataError(f"No bars for {key}")
        if timeframe not in ALLOWED_TIMEFRAMES:
            raise MarketDataError(f"Unsupported timeframe: {timeframe}")

        cache_key = (key, timeframe)
        cached = chart_bars_cache.get(cache_key)
        if cached is not None:
            return cached

        self.fetch_counts[cache_key] = self.fetch_counts.get(cache_key, 0) + 1
        if timeframe == "1Day":
            daily = self.get_daily_bars(key, days or ALLOWED_TIMEFRAMES["1Day"]["days"])
            bars = [
                IntradayBar(
                    timestamp=datetime(
                        bar.date.year,
                        bar.date.month,
                        bar.date.day,
                        15,
                        0,
                        tzinfo=timezone.utc,
                    ),
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    volume=bar.volume,
                )
                for bar in daily
            ]
        else:
            bars = list(self._intraday.get(key, []))

        ttl = (
            DAILY_CHART_TTL_SECONDS
            if timeframe == "1Day"
            else INTRADAY_TTL_SECONDS
        )
        chart_bars_cache.set(cache_key, bars, ttl)
        return bars

    def get_news(self, symbol: str, limit: int = 10) -> list[NewsItem]:
        if self.news_fail:
            raise MarketDataError("News provider unavailable")
        key = symbol.strip().upper()
        items = list(self.news_by_symbol.get(key, []))
        items.sort(key=lambda item: item.created_at, reverse=True)
        return items[:limit]

    def get_news_for_symbols(
        self,
        symbols: list[str],
        limit: int = 10,
    ) -> dict[str, list[NewsItem]]:
        if self.news_fail:
            raise MarketDataError("News provider unavailable")
        return {
            symbol.strip().upper(): self.get_news(symbol, limit=limit)
            for symbol in symbols
            if symbol and symbol.strip()
        }


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def _override_get_db() -> Generator[Session, None, None]:
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def fake_provider(client: TestClient) -> FakeProvider:
    provider = FakeProvider()
    app.dependency_overrides[get_market_data_provider] = lambda: provider
    return provider
