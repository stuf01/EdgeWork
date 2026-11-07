"""API tests for checklists using the fake market-data provider."""

from __future__ import annotations

from fastapi.testclient import TestClient


CALC = {
    "account_size": "10000",
    "risk_percent": "1",
    "entry": "40.00",
    "stop": "39.50",
    "target": "41.50",
}


def _ensure_default(client: TestClient) -> dict:
    resp = client.get("/api/checklists")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) >= 1
    assert rows[0]["name"] == "Breakout basics"
    return rows[0]


def test_evaluate_endpoint(client: TestClient, fake_provider) -> None:
    checklist = _ensure_default(client)
    resp = client.post(
        f"/api/checklists/{checklist['id']}/evaluate",
        json={
            "symbol": "GOOD",
            "entry": "25.00",
            "stop": "24.00",
            "target": "28.00",
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["checklist_id"] == checklist["id"]
    assert "results" in payload
    assert isinstance(payload["score"], int)
    assert payload["verdict"] in (
        "Meets your rules",
        "Does not meet your rules",
    )
    # GOOD has strong gap/rvol/news; R:R = 3/1 = 3
    labels = {row["label"]: row for row in payload["results"]}
    assert labels["Gap percent"]["passed"] is True
    assert labels["Relative volume"]["passed"] is True
    assert labels["Has recent news"]["passed"] is True
    assert labels["Risk / reward"]["passed"] is True


def test_evaluate_missing_data_unknown(client: TestClient, fake_provider) -> None:
    checklist = _ensure_default(client)
    # BAD has snapshot but bar errors — some fields unknown
    resp = client.post(
        f"/api/checklists/{checklist['id']}/evaluate",
        json={
            "symbol": "BAD",
            "entry": "10.00",
            "stop": "9.50",
            "target": "12.00",
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["unknown_count"] >= 1
    # Request still succeeds
    assert "verdict" in payload


def test_invalid_rule_type_rejected(client: TestClient) -> None:
    resp = client.post(
        "/api/checklists",
        json={
            "name": "Bad rules",
            "description": None,
            "rules": [
                {
                    "position": 0,
                    "label": "Nope",
                    "rule_type": "not_a_real_rule",
                    "operator": ">=",
                    "threshold": "1",
                    "required": False,
                }
            ],
        },
    )
    assert resp.status_code == 422
    assert "rule_type" in resp.json()["detail"]


def test_checklist_score_saved_with_plan(
    client: TestClient,
    fake_provider,
) -> None:
    checklist = _ensure_default(client)
    resp = client.post(
        "/api/plans",
        json={
            **CALC,
            "symbol": "GOOD",
            "entry": "25.00",
            "stop": "24.00",
            "target": "28.00",
            "checklist_id": checklist["id"],
            "is_paper": True,
        },
    )
    assert resp.status_code == 201
    created = resp.json()
    assert created["checklist_id"] == checklist["id"]
    assert created["checklist_score"] is not None
    assert isinstance(created["checklist_score"], int)


def test_journal_stats_includes_checklist_breakdown(
    client: TestClient,
    fake_provider,
) -> None:
    checklist = _ensure_default(client)
    create = client.post(
        "/api/plans",
        json={
            **CALC,
            "symbol": "GOOD",
            "entry": "25.00",
            "stop": "24.00",
            "target": "28.00",
            "checklist_id": checklist["id"],
        },
    )
    plan_id = create.json()["id"]
    client.patch(
        f"/api/plans/{plan_id}",
        json={
            "status": "open",
            "actual_entry": "25.00",
            "shares_traded": 100,
        },
    )
    client.patch(
        f"/api/plans/{plan_id}",
        json={
            "status": "closed",
            "actual_exit": "26.00",
            "exit_reason": "manual_exit",
        },
    )
    stats = client.get("/api/journal/stats")
    assert stats.status_code == 200
    body = stats.json()
    assert "by_checklist_score" in body
    assert "met" in body["by_checklist_score"]
    assert "below" in body["by_checklist_score"]
