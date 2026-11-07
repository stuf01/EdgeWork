"""API tests using FastAPI TestClient and in-memory SQLite."""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import TradePlan


CALC_BODY = {
    "account_size": "10000",
    "risk_percent": "1",
    "entry": "40.00",
    "stop": "39.50",
    "target": "41.50",
}


def test_calculate_endpoint(client: TestClient) -> None:
    response = client.post("/api/plans/calculate", json=CALC_BODY)
    assert response.status_code == 200
    data = response.json()
    assert data["shares"] == 200
    assert data["max_risk_dollars"] == "100"
    assert data["risk_per_share"] == "0.50"
    assert data["reward_per_share"] == "1.50"
    assert data["risk_reward_ratio"] == "3"
    assert data["exceeds_account"] is False


def test_calculate_validation_error(client: TestClient) -> None:
    bad = {**CALC_BODY, "stop": "41.00"}
    response = client.post("/api/plans/calculate", json=bad)
    assert response.status_code == 422
    assert "detail" in response.json()


def test_save_list_delete_plans(client: TestClient) -> None:
    create_body = {**CALC_BODY, "symbol": "aapl", "notes": "test note"}
    create_resp = client.post("/api/plans", json=create_body)
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["symbol"] == "AAPL"
    assert created["shares"] == 200
    assert created["notes"] == "test note"
    plan_id = created["id"]

    list_resp = client.get("/api/plans")
    assert list_resp.status_code == 200
    plans = list_resp.json()
    assert len(plans) == 1
    assert plans[0]["id"] == plan_id

    delete_resp = client.delete(f"/api/plans/{plan_id}")
    assert delete_resp.status_code == 204

    list_after = client.get("/api/plans")
    assert list_after.json() == []


def test_delete_not_found(client: TestClient) -> None:
    response = client.delete("/api/plans/9999")
    assert response.status_code == 404


def test_decimal_round_trip(db_session: Session) -> None:
    """Confirm DecimalString stores and returns Decimal, not float."""
    plan = TradePlan(
        symbol="TEST",
        account_size=Decimal("10000"),
        risk_percent=Decimal("1"),
        entry=Decimal("40.10"),
        stop=Decimal("39.50"),
        target=Decimal("41.50"),
        shares=200,
        actual_risk=Decimal("100"),
        risk_reward=Decimal("3"),
        notes=None,
    )
    db_session.add(plan)
    db_session.commit()
    plan_id = plan.id
    db_session.expire_all()

    loaded = db_session.get(TradePlan, plan_id)
    assert loaded is not None
    assert isinstance(loaded.entry, Decimal)
    assert loaded.entry == Decimal("40.10")
    assert not isinstance(loaded.entry, float)
