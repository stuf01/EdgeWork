"""API tests for earnings endpoints and enrichment (fake provider)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import FakeEarningsProvider


def test_ticker_earnings_upcoming(
    client: TestClient,
    fake_provider,
    fake_earnings: FakeEarningsProvider,
) -> None:
    resp = client.get("/api/tickers/GOOD/earnings")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["symbol"] == "GOOD"
    assert body["days_until_earnings"] == 1
    assert body["earnings_risk"] == "today_or_tomorrow"
    assert body["time_of_day"] == "after_close"
    assert body["next_earnings_date"] is not None


def test_ticker_earnings_none_upcoming(
    client: TestClient,
    fake_provider,
    fake_earnings: FakeEarningsProvider,
) -> None:
    resp = client.get("/api/tickers/FLAT/earnings")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["next_earnings_date"] is None
    assert body["days_until_earnings"] is None
    assert body["earnings_risk"] == "none"


def test_ticker_detail_includes_earnings(
    client: TestClient,
    fake_provider,
    fake_earnings: FakeEarningsProvider,
) -> None:
    resp = client.get("/api/tickers/GOOD/detail")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["days_until_earnings"] == 1
    assert body["earnings_risk"] == "today_or_tomorrow"
    assert body["earnings_time_of_day"] == "after_close"


def test_ticker_detail_earnings_failure_leaves_null(
    client: TestClient,
    fake_provider,
    fake_earnings: FakeEarningsProvider,
) -> None:
    fake_earnings.fail = True
    resp = client.get("/api/tickers/GOOD/detail")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["next_earnings_date"] is None
    assert body["days_until_earnings"] is None
    assert body["earnings_risk"] is None


def test_scanner_includes_earnings_and_survives_failure(
    client: TestClient,
    fake_provider,
    fake_earnings: FakeEarningsProvider,
) -> None:
    client.post("/api/watchlist", json={"symbol": "GOOD"})
    client.post("/api/watchlist", json={"symbol": "FLAT"})
    ok = client.get(
        "/api/scanner",
        params={
            "min_price": "1",
            "max_price": "1000",
            "min_gap_percent": "0",
            "min_relative_volume": "0.01",
            "min_avg_volume": "1",
        },
    )
    assert ok.status_code == 200, ok.text
    rows = {row["symbol"]: row for row in ok.json()["results"]}
    assert "GOOD" in rows
    assert rows["GOOD"]["earnings_risk"] == "today_or_tomorrow"
    assert rows["GOOD"]["days_until_earnings"] == 1
    if "FLAT" in rows:
        assert rows["FLAT"]["earnings_risk"] in ("none", None)

    fake_earnings.fail = True
    again = client.get(
        "/api/scanner",
        params={
            "min_price": "1",
            "max_price": "1000",
            "min_gap_percent": "0",
            "min_relative_volume": "0.01",
            "min_avg_volume": "1",
        },
    )
    assert again.status_code == 200, again.text
    assert again.json()["scanned"] >= 1


def test_earnings_endpoint_provider_failure(
    client: TestClient,
    fake_provider,
    fake_earnings: FakeEarningsProvider,
) -> None:
    fake_earnings.fail = True
    resp = client.get("/api/tickers/GOOD/earnings")
    assert resp.status_code == 502


def test_checklist_days_to_earnings_rule() -> None:
    from decimal import Decimal

    from app.checklist import ChecklistRuleSpec, evaluate, score
    from app.earnings import DAYS_TO_EARNINGS_FAR

    rule = ChecklistRuleSpec(
        label="Days to earnings",
        rule_type="days_to_earnings",
        operator=">=",
        threshold=Decimal("2"),
        required=True,
    )
    fail = evaluate([rule], {"days_to_earnings": Decimal("1")})
    assert fail[0].passed is False
    assert "Days to earnings" in score(fail).required_failed

    ok = evaluate([rule], {"days_to_earnings": Decimal(DAYS_TO_EARNINGS_FAR)})
    assert ok[0].passed is True
    assert score(ok).verdict == "Meets your rules"
