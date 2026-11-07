"""API tests for journal PATCH and stats endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient


CALC_BODY = {
    "account_size": "10000",
    "risk_percent": "1",
    "entry": "40.00",
    "stop": "39.50",
    "target": "41.50",
}


def _create_plan(client: TestClient, **extra) -> dict:
    body = {**CALC_BODY, "symbol": "AAPL", "notes": "journal", **extra}
    resp = client.post("/api/plans", json=body)
    assert resp.status_code == 201
    return resp.json()


def test_create_plan_defaults_journal_fields(client: TestClient) -> None:
    created = _create_plan(client, setup_tag="breakout", is_paper=True)
    assert created["status"] == "planned"
    assert created["is_paper"] is True
    assert created["setup_tag"] == "breakout"
    assert created["actual_entry"] is None


def test_mark_open_and_close(client: TestClient) -> None:
    created = _create_plan(client)
    plan_id = created["id"]

    open_resp = client.patch(
        f"/api/plans/{plan_id}",
        json={"status": "open", "actual_entry": "40.05", "shares_traded": 200},
    )
    assert open_resp.status_code == 200
    opened = open_resp.json()
    assert opened["status"] == "open"
    assert opened["actual_entry"] == "40.05"
    assert opened["shares_traded"] == 200
    assert opened["opened_at"] is not None

    close_resp = client.patch(
        f"/api/plans/{plan_id}",
        json={
            "status": "closed",
            "actual_exit": "41.00",
            "exit_reason": "target_hit",
            "lessons": "Held for target",
        },
    )
    assert close_resp.status_code == 200
    closed = close_resp.json()
    assert closed["status"] == "closed"
    assert closed["closed_at"] is not None
    assert closed["exit_reason"] == "target_hit"
    assert closed["lessons"] == "Held for target"
    # (41 - 40.05) * 200 = 190
    assert closed["realized_pnl"] == "190.00"
    assert closed["r_multiple"] is not None


def test_close_without_required_fields_returns_422(client: TestClient) -> None:
    created = _create_plan(client)
    plan_id = created["id"]
    resp = client.patch(f"/api/plans/{plan_id}", json={"status": "closed"})
    assert resp.status_code == 422
    assert "actual_entry" in resp.json()["detail"]


def test_skip_plan(client: TestClient) -> None:
    created = _create_plan(client)
    resp = client.patch(f"/api/plans/{created['id']}", json={"status": "skipped"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "skipped"


def test_journal_stats_with_filters(client: TestClient) -> None:
    paper = _create_plan(client, symbol="PAPER", setup_tag="pullback", is_paper=True)
    real = _create_plan(client, symbol="REAL", setup_tag="breakout", is_paper=False)

    for plan_id, exit_price in ((paper["id"], "41.00"), (real["id"], "39.00")):
        client.patch(
            f"/api/plans/{plan_id}",
            json={
                "status": "open",
                "actual_entry": "40.00",
                "shares_traded": 100,
            },
        )
        client.patch(
            f"/api/plans/{plan_id}",
            json={
                "status": "closed",
                "actual_exit": exit_price,
                "exit_reason": "manual_exit",
            },
        )

    all_stats = client.get("/api/journal/stats")
    assert all_stats.status_code == 200
    payload = all_stats.json()
    assert payload["overall"]["total_trades"] == 2
    assert len(payload["by_tag"]) == 2
    assert len(payload["cumulative_pnl"]) == 2

    paper_only = client.get("/api/journal/stats", params={"is_paper": True})
    assert paper_only.json()["overall"]["total_trades"] == 1
    assert paper_only.json()["overall"]["wins"] == 1

    tag_only = client.get("/api/journal/stats", params={"setup_tag": "breakout"})
    assert tag_only.json()["overall"]["total_trades"] == 1
    assert tag_only.json()["overall"]["losses"] == 1

    future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    empty = client.get("/api/journal/stats", params={"from": future})
    assert empty.json()["overall"]["total_trades"] == 0
