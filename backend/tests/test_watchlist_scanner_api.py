"""API tests for watchlist and scanner with a fake market data provider."""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from tests.conftest import FakeProvider


def test_watchlist_add_list_delete(client: TestClient) -> None:
    create = client.post("/api/watchlist", json={"symbol": "aapl", "notes": "mega"})
    assert create.status_code == 201
    body = create.json()
    assert body["symbol"] == "AAPL"
    assert body["notes"] == "mega"

    dup = client.post("/api/watchlist", json={"symbol": "AAPL"})
    assert dup.status_code == 409

    listed = client.get("/api/watchlist")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    deleted = client.delete("/api/watchlist/AAPL")
    assert deleted.status_code == 204
    assert client.get("/api/watchlist").json() == []

    missing = client.delete("/api/watchlist/AAPL")
    assert missing.status_code == 404


def test_scanner_filters_and_errors(
    client: TestClient,
    fake_provider: FakeProvider,
) -> None:
    for symbol in ("GOOD", "FLAT", "CHEAP", "BAD", "MISSING"):
        resp = client.post("/api/watchlist", json={"symbol": symbol})
        assert resp.status_code == 201

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
    assert payload["scanned"] == 5
    symbols = [row["symbol"] for row in payload["results"]]
    assert symbols == ["GOOD"]
    assert Decimal(payload["results"][0]["gap_percent"]) == Decimal("20")

    excluded_symbols = {item["symbol"] for item in payload["excluded"]}
    assert excluded_symbols == {"FLAT", "CHEAP"}
    assert all("reason" in item for item in payload["excluded"])

    error_symbols = {item["symbol"] for item in payload["errors"]}
    assert "BAD" in error_symbols
    assert "MISSING" in error_symbols
    assert "FLAT" not in symbols
    assert "CHEAP" not in symbols
    assert "FLAT" not in error_symbols
    assert "CHEAP" not in error_symbols
