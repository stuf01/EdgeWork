"""API tests for ticker news and scanner news enrichment."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import FakeProvider


def test_ticker_news_normal(
    client: TestClient,
    fake_provider: FakeProvider,
) -> None:
    response = client.get("/api/tickers/GOOD/news")
    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "GOOD"
    assert len(body["items"]) == 2
    assert body["count_last_24h"] == 1
    assert body["has_recent_news"] is True
    assert body["items"][0]["headline"] == "GOOD pops on earnings"


def test_ticker_news_empty(
    client: TestClient,
    fake_provider: FakeProvider,
) -> None:
    response = client.get("/api/tickers/FLAT/news")
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["count_last_24h"] == 0
    assert body["has_recent_news"] is False


def test_ticker_news_provider_failure(
    client: TestClient,
    fake_provider: FakeProvider,
) -> None:
    fake_provider.news_fail = True
    response = client.get("/api/tickers/GOOD/news")
    assert response.status_code == 502
    assert "News provider unavailable" in response.json()["detail"]


def test_scanner_survives_news_failure(
    client: TestClient,
    fake_provider: FakeProvider,
) -> None:
    fake_provider.news_fail = True
    assert client.post("/api/watchlist", json={"symbol": "GOOD"}).status_code == 201
    scan = client.get(
        "/api/scanner",
        params={
            "min_price": "5",
            "max_price": "500",
            "min_gap_percent": "2",
            "min_relative_volume": "1.5",
            "min_avg_volume": "500000",
        },
    )
    assert scan.status_code == 200
    payload = scan.json()
    assert len(payload["results"]) == 1
    row = payload["results"][0]
    assert row["symbol"] == "GOOD"
    assert row["has_recent_news"] is None
    assert row["count_last_24h"] is None


def test_scanner_includes_news_flags(
    client: TestClient,
    fake_provider: FakeProvider,
) -> None:
    assert client.post("/api/watchlist", json={"symbol": "GOOD"}).status_code == 201
    scan = client.get(
        "/api/scanner",
        params={
            "min_price": "5",
            "max_price": "500",
            "min_gap_percent": "2",
            "min_relative_volume": "1.5",
            "min_avg_volume": "500000",
        },
    )
    assert scan.status_code == 200
    row = scan.json()["results"][0]
    assert row["has_recent_news"] is True
    assert row["count_last_24h"] == 1
