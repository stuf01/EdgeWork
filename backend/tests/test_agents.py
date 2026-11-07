"""Unit and API tests for the six-agent paper pipeline (no network)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.agents import PAPER_URL_REQUIRED
from app.agents.kira import run_kira
from app.agents.luma import run_luma
from app.agents.orin import run_orin
from app.agents.paper_client import FakePaperClient, PaperTradingError
from app.agents.schemas import (
    KiraInput,
    LumaInput,
    NovaCandidate,
    OrinInput,
    OrinScore,
    VeskCheckInput,
    VeskInput,
    VeskResult,
)
from app.agents.vesk import run_vesk
from app.models import BacktestRun, Proposal
from tests.conftest import FakeProvider


@pytest.fixture()
def fake_broker(client: TestClient):
    broker = FakePaperClient()
    import app.agents.api as agents_api

    agents_api._paper_broker_override = broker
    yield broker
    agents_api._paper_broker_override = None


def _candidate(symbol: str = "GOOD") -> NovaCandidate:
    return NovaCandidate(
        symbol=symbol,
        entry=Decimal("25.01"),
        stop=Decimal("24.00"),
        target=Decimal("27.03"),
        checklist_score=85,
        gap_percent=Decimal("5"),
        relative_volume=Decimal("3"),
        last_price=Decimal("25.00"),
        has_recent_news=True,
        days_until_earnings=10,
    )


def _seed_backtest(db_session: Session, *, trades: int = 120, expectancy: str = "0.5") -> None:
    summary = {
        "summary": {
            "total_trades": trades,
            "wins": trades // 2,
            "losses": trades // 2,
            "win_rate": "50",
            "avg_win": "100",
            "avg_loss": "80",
            "avg_r": "0.5",
            "expectancy_r": expectancy,
            "total_pnl": "1000",
            "best_trade": "200",
            "worst_trade": "-100",
            "max_drawdown": "50",
        },
        "by_year": {},
        "equity_curve": [],
        "errors": [],
        "skipped_days": 0,
    }
    run = BacktestRun(
        name="gate",
        parameters="{}",
        symbols='["GOOD"]',
        start_date=datetime.now(timezone.utc).date() - timedelta(days=30),
        end_date=datetime.now(timezone.utc).date(),
        summary=json.dumps(summary),
        trades="[]",
    )
    db_session.add(run)
    db_session.commit()


def test_orin_score_bounds_and_low_confidence(fake_provider: FakeProvider) -> None:
    out = run_orin(
        fake_provider,
        OrinInput(cycle_id="c1", candidates=[_candidate()]),
    )
    assert len(out.scores) == 1
    score = out.scores[0]
    assert 0 <= score.score <= 100
    # Fake provider has short history → low confidence.
    assert score.low_confidence is True


def test_vesk_lists_multiple_reasons() -> None:
    check = VeskCheckInput(
        cycle_id="c1",
        symbol="GOOD",
        entry=Decimal("25"),
        stop=Decimal("26"),  # invalid
        target=Decimal("24"),  # invalid
        account_size=Decimal("10000"),
        risk_percent=Decimal("1"),
        buying_power=Decimal("10"),
        open_positions=3,
        max_open_positions=3,
        trades_today=3,
        max_trades_per_day=3,
        daily_pnl=Decimal("-500"),
        daily_loss_limit_percent=Decimal("3"),
        has_open_or_pending=True,
        days_until_earnings=1,
        market_open=False,
        within_open_buffer=True,
    )
    result = run_vesk(VeskInput(cycle_id="c1", checks=[check])).results[0]
    assert result.approved is False
    assert len(result.reasons) >= 5
    assert "stop_not_below_entry" in result.reasons
    assert "earnings_within_2_days" in result.reasons


def test_luma_never_proposes_vetoed() -> None:
    candidate = _candidate()
    orin = OrinScore(
        symbol="GOOD",
        score=90,
        expected_move_percent=Decimal("2"),
        sample_count=50,
        low_confidence=False,
    )
    vesk = VeskResult(
        symbol="GOOD",
        approved=False,
        shares=0,
        reasons=["max_open_positions", "earnings_within_2_days"],
    )
    out = run_luma(
        LumaInput(
            cycle_id="c1",
            candidates=[candidate],
            orin_scores=[orin],
            vesk_results=[vesk],
            min_orin_score=60,
            min_checklist_score=70,
        )
    )
    assert out.decisions[0].decision == "VETO"
    assert out.decisions[0].decision != "PROPOSE"


def test_kira_refuses_non_paper_url(db_session: Session) -> None:
    with pytest.raises(PaperTradingError):
        FakePaperClient(paper_url="https://api.alpaca.markets")

    broker = FakePaperClient()
    result = run_kira(
        db_session,
        broker,
        KiraInput(
            proposal_id=1,
            symbol="GOOD",
            status="approved",
            entry=Decimal("25"),
            stop=Decimal("24"),
            target=Decimal("27"),
            shares=10,
            paper_url="https://api.alpaca.markets",
            client_order_id="1",
        ),
        account_size=Decimal("10000"),
        risk_percent=Decimal("1"),
    )
    assert result.executed is False
    assert "paper" in (result.reason or "").lower()


def test_kira_refuses_unapproved_and_idempotent(
    db_session: Session,
) -> None:
    broker = FakePaperClient()
    proposal = Proposal(
        cycle_id="c1",
        symbol="GOOD",
        status="pending",
        entry=Decimal("25"),
        stop=Decimal("24"),
        target=Decimal("27"),
        shares=10,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    db_session.add(proposal)
    db_session.commit()
    db_session.refresh(proposal)

    refused = run_kira(
        db_session,
        broker,
        KiraInput(
            proposal_id=proposal.id,
            symbol="GOOD",
            status="pending",
            entry=proposal.entry,
            stop=proposal.stop,
            target=proposal.target,
            shares=10,
            paper_url=PAPER_URL_REQUIRED,
            client_order_id=str(proposal.id),
        ),
        account_size=Decimal("10000"),
        risk_percent=Decimal("1"),
    )
    assert refused.executed is False

    proposal.status = "approved"
    db_session.commit()
    first = run_kira(
        db_session,
        broker,
        KiraInput(
            proposal_id=proposal.id,
            symbol="GOOD",
            status="approved",
            entry=proposal.entry,
            stop=proposal.stop,
            target=proposal.target,
            shares=10,
            last_price=Decimal("25.00"),
            expires_at=proposal.expires_at,
            paper_url=PAPER_URL_REQUIRED,
            client_order_id=str(proposal.id),
        ),
        account_size=Decimal("10000"),
        risk_percent=Decimal("1"),
    )
    assert first.executed is True
    assert broker.submit_count == 1

    second = run_kira(
        db_session,
        broker,
        KiraInput(
            proposal_id=proposal.id,
            symbol="GOOD",
            status="approved",
            entry=proposal.entry,
            stop=proposal.stop,
            target=proposal.target,
            shares=10,
            last_price=Decimal("25.00"),
            expires_at=proposal.expires_at,
            paper_url=PAPER_URL_REQUIRED,
            client_order_id=str(proposal.id),
        ),
        account_size=Decimal("10000"),
        risk_percent=Decimal("1"),
    )
    assert second.executed is True
    assert broker.submit_count == 1  # idempotent client_order_id


def test_kill_switch_and_disabled_stop_cycle(
    client: TestClient,
    db_session: Session,
    fake_provider: FakeProvider,
    fake_broker,
) -> None:
    _seed_backtest(db_session)
    # Enable then kill
    enabled = client.put("/api/agents/settings", json={"enabled": True})
    assert enabled.status_code == 200, enabled.text
    killed = client.post("/api/agents/kill-switch")
    assert killed.status_code == 200
    assert killed.json()["kill_switch"] is True
    assert killed.json()["enabled"] is False

    skipped = client.post("/api/agents/run-cycle?force=true")
    assert skipped.status_code == 200
    assert skipped.json()["skipped"] is True
    assert skipped.json()["skip_reason"] == "kill_switch"


def test_backtest_gate_blocks_enable(
    client: TestClient,
    db_session: Session,
    fake_broker,
) -> None:
    resp = client.put("/api/agents/settings", json={"enabled": True})
    assert resp.status_code == 422
    assert "backtest" in resp.json()["detail"].lower()

    _seed_backtest(db_session, trades=10, expectancy="-0.1")
    weak = client.put("/api/agents/settings", json={"enabled": True})
    assert weak.status_code == 422

    confirmed = client.put(
        "/api/agents/settings",
        json={"enabled": True, "confirm_weak_backtest": True},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["enabled"] is True


def test_cycle_writes_events_and_dash(
    client: TestClient,
    db_session: Session,
    fake_provider: FakeProvider,
    fake_broker,
    fake_earnings,
) -> None:
    _seed_backtest(db_session)
    client.post("/api/watchlist", json={"symbol": "GOOD"})
    client.put(
        "/api/agents/settings",
        json={"enabled": True, "confirm_weak_backtest": True},
    )
    cycle = client.post("/api/agents/run-cycle?force=true")
    assert cycle.status_code == 200, cycle.text
    body = cycle.json()
    assert body["skipped"] is False

    events = client.get("/api/agents/events")
    assert events.status_code == 200
    agents = {row["agent"] for row in events.json()}
    assert {"SYSTEM", "NOVA", "ORIN", "VESK", "LUMA"} <= agents

    review = client.post("/api/agents/review/run")
    assert review.status_code == 200
    assert "report" in review.json()
    latest = client.get("/api/agents/review/latest")
    assert latest.status_code == 200


def test_cannot_approve_vetoed_proposal(
    client: TestClient,
    db_session: Session,
    fake_broker,
) -> None:
    proposal = Proposal(
        cycle_id="c-veto",
        symbol="GOOD",
        status="vetoed",
        entry=Decimal("25"),
        stop=Decimal("24"),
        target=Decimal("27"),
        shares=0,
        vesk_result=json.dumps({"approved": False, "reasons": ["max_open_positions"]}),
        luma_reasoning="VESK vetoed",
    )
    db_session.add(proposal)
    db_session.commit()
    db_session.refresh(proposal)

    resp = client.post(f"/api/agents/proposals/{proposal.id}/approve")
    assert resp.status_code == 409
    assert "veto" in resp.json()["detail"].lower()
