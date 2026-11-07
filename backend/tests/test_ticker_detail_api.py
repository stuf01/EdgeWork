"""API tests for ticker detail using the fake provider."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import FakeProvider


def test_ticker_detail_success(
    client: TestClient,
    fake_provider: FakeProvider,
) -> None:
    response = client.get("/api/tickers/GOOD/detail")
    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "GOOD"
    assert body["timeframe"] == "5Min"
    assert body["last_price"] == "25.00"
    assert len(body["bars"]) == 3
    assert len(body["vwap"]) == 3
    assert body["levels"]["today_open"] == "24.00"
    assert body["levels"]["prev_day_high"] is not None
    assert body["sma_20"] is not None
    assert body["gap_percent"] in ("20", "20.0")


def test_ticker_detail_unknown_symbol(
    client: TestClient,
    fake_provider: FakeProvider,
) -> None:
    response = client.get("/api/tickers/ZZZZ/detail")
    assert response.status_code == 404
    assert "ZZZZ" in response.json()["detail"]


def test_ticker_detail_rejects_invalid_timeframe(
    client: TestClient,
    fake_provider: FakeProvider,
) -> None:
    response = client.get("/api/tickers/GOOD/detail", params={"timeframe": "3Min"})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "Invalid timeframe" in detail
    assert "5Min" in detail


def test_ticker_detail_vwap_present_for_5min_absent_for_1day(
    client: TestClient,
    fake_provider: FakeProvider,
) -> None:
    five = client.get("/api/tickers/GOOD/detail", params={"timeframe": "5Min"})
    assert five.status_code == 200
    assert len(five.json()["vwap"]) > 0

    daily = client.get("/api/tickers/GOOD/detail", params={"timeframe": "1Day"})
    assert daily.status_code == 200
    body = daily.json()
    assert body["timeframe"] == "1Day"
    assert body["vwap"] == []
    assert len(body["bars"]) > 0


def test_chart_bars_cache_keeps_timeframes_separate(
    client: TestClient,
    fake_provider: FakeProvider,
) -> None:
    first = client.get("/api/tickers/GOOD/detail", params={"timeframe": "5Min"})
    second = client.get("/api/tickers/GOOD/detail", params={"timeframe": "5Min"})
    other = client.get("/api/tickers/GOOD/detail", params={"timeframe": "1Min"})
    assert first.status_code == 200
    assert second.status_code == 200
    assert other.status_code == 200

    assert fake_provider.fetch_counts[("GOOD", "5Min")] == 1
    assert fake_provider.fetch_counts[("GOOD", "1Min")] == 1
