"""API tests for backtest endpoints (fake provider, no network)."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient


def test_backtest_run_list_get_delete(client: TestClient, fake_provider) -> None:
    today = date.today()
    start = today - timedelta(days=40)
    body = {
        "symbols": ["GOOD"],
        "start_date": start.isoformat(),
        "end_date": today.isoformat(),
        "name": "smoke",
        "min_gap_percent": "0",
        "min_relative_volume": "0.1",
        "min_avg_volume": "1",
        "min_price": "1",
        "cost_per_share": "0",
    }
    created = client.post("/api/backtests", json=body)
    assert created.status_code == 201, created.text
    payload = created.json()
    assert payload["id"] is not None
    assert payload["name"] == "smoke"
    assert "summary" in payload
    assert "trades" in payload
    assert "equity_curve" in payload
    run_id = payload["id"]

    listed = client.get("/api/backtests")
    assert listed.status_code == 200
    rows = listed.json()
    assert any(row["id"] == run_id for row in rows)
    assert "trades" not in rows[0]
    # List payload must expose flat JournalStats fields (not the nested blob).
    assert "total_trades" in rows[0]["summary"]
    assert isinstance(rows[0]["summary"]["total_trades"], int)
    assert "by_year" not in rows[0]["summary"]

    detail = client.get(f"/api/backtests/{run_id}")
    assert detail.status_code == 200
    assert detail.json()["id"] == run_id
    assert "trades" in detail.json()

    deleted = client.delete(f"/api/backtests/{run_id}")
    assert deleted.status_code == 204
    missing = client.get(f"/api/backtests/{run_id}")
    assert missing.status_code == 404


def test_backtest_validation_too_many_symbols(client: TestClient, fake_provider) -> None:
    today = date.today()
    symbols = [f"S{i}" for i in range(51)]
    resp = client.post(
        "/api/backtests",
        json={
            "symbols": symbols,
            "start_date": (today - timedelta(days=10)).isoformat(),
            "end_date": today.isoformat(),
        },
    )
    assert resp.status_code == 422
    assert "50" in resp.json()["detail"]


def test_backtest_validation_date_order(client: TestClient, fake_provider) -> None:
    today = date.today()
    resp = client.post(
        "/api/backtests",
        json={
            "symbols": ["GOOD"],
            "start_date": today.isoformat(),
            "end_date": (today - timedelta(days=5)).isoformat(),
        },
    )
    assert resp.status_code == 422


def test_backtest_bad_symbol_lands_in_errors(
    client: TestClient,
    fake_provider,
) -> None:
    today = date.today()
    resp = client.post(
        "/api/backtests",
        json={
            "symbols": ["GOOD", "BAD"],
            "start_date": (today - timedelta(days=40)).isoformat(),
            "end_date": today.isoformat(),
            "min_gap_percent": "0",
            "min_relative_volume": "0.1",
            "min_avg_volume": "1",
            "min_price": "1",
        },
    )
    assert resp.status_code == 201
    errors = resp.json()["errors"]
    assert any(err["symbol"] == "BAD" for err in errors)


def test_backtest_use_watchlist(client: TestClient, fake_provider) -> None:
    client.post("/api/watchlist", json={"symbol": "GOOD"})
    today = date.today()
    resp = client.post(
        "/api/backtests",
        json={
            "use_watchlist": True,
            "start_date": (today - timedelta(days=40)).isoformat(),
            "end_date": today.isoformat(),
            "min_gap_percent": "0",
            "min_relative_volume": "0.1",
            "min_avg_volume": "1",
            "min_price": "1",
        },
    )
    assert resp.status_code == 201
    assert "GOOD" in resp.json()["symbols"]
