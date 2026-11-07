"""HTTP endpoints for the paper agent pipeline."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import AGENT_JOBS, PAPER_URL_REQUIRED
from app.agents import log_detail
from app.agents.cycle import run_cycle
from app.agents.dash import run_dash
from app.agents.events import log_event
from app.agents.kira import run_kira
from app.agents.paper_client import AlpacaPaperClient, PaperTradingError
from app.agents.schemas import KiraInput
from app.agents.service import (
    AgentSettingsError,
    backtest_gate_status,
    get_or_create_settings,
    latest_review,
    list_proposals,
    save_review,
    toggle_kill_switch,
    update_settings,
)
from app.database import get_db
from app.models import AgentEvent, Proposal
from app.providers import get_earnings_provider, get_provider
from app.providers.base import MarketDataError, MarketDataProvider

_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_ENV_PATH, override=True)

router = APIRouter(prefix="/api/agents", tags=["agents"])

# Tests may override this dependency.
_paper_broker_override: Any = None


def get_paper_broker():
    if _paper_broker_override is not None:
        return _paper_broker_override
    try:
        return AlpacaPaperClient()
    except PaperTradingError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def get_market_data_provider() -> MarketDataProvider:
    try:
        return get_provider()
    except MarketDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


class AgentSettingsUpdate(BaseModel):
    enabled: Optional[bool] = None
    kill_switch: Optional[bool] = None
    max_open_positions: Optional[int] = Field(default=None, ge=1, le=20)
    max_trades_per_day: Optional[int] = Field(default=None, ge=1, le=50)
    daily_loss_limit_percent: Optional[Decimal] = Field(default=None, gt=0, le=100)
    risk_per_trade_percent: Optional[Decimal] = Field(default=None, gt=0, le=100)
    proposal_ttl_minutes: Optional[int] = Field(default=None, ge=1, le=240)
    min_orin_score: Optional[int] = Field(default=None, ge=0, le=100)
    min_checklist_score: Optional[int] = Field(default=None, ge=0, le=100)
    checklist_id: Optional[int] = None
    cycle_interval_minutes: Optional[int] = Field(default=None, ge=1, le=60)
    scheduler_enabled: Optional[bool] = None
    confirm_weak_backtest: Optional[bool] = None


def _settings_payload(settings, gate: dict[str, Any]) -> dict[str, Any]:
    return {
        "enabled": settings.enabled,
        "kill_switch": settings.kill_switch,
        "max_open_positions": settings.max_open_positions,
        "max_trades_per_day": settings.max_trades_per_day,
        "daily_loss_limit_percent": format(settings.daily_loss_limit_percent, "f"),
        "risk_per_trade_percent": format(settings.risk_per_trade_percent, "f"),
        "proposal_ttl_minutes": settings.proposal_ttl_minutes,
        "min_orin_score": settings.min_orin_score,
        "min_checklist_score": settings.min_checklist_score,
        "checklist_id": settings.checklist_id,
        "cycle_interval_minutes": settings.cycle_interval_minutes,
        "scheduler_enabled": settings.scheduler_enabled,
        "backtest_weak_confirmed": settings.backtest_weak_confirmed,
        "backtest_gate": gate,
        "agent_jobs": AGENT_JOBS,
        "paper_url_required": PAPER_URL_REQUIRED,
    }


def _proposal_payload(row: Proposal) -> dict[str, Any]:
    vesk = None
    if row.vesk_result:
        try:
            vesk = json.loads(row.vesk_result)
        except json.JSONDecodeError:
            vesk = {"raw": row.vesk_result}
    return {
        "id": row.id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "cycle_id": row.cycle_id,
        "symbol": row.symbol,
        "status": row.status,
        "entry": format(row.entry, "f"),
        "stop": format(row.stop, "f"),
        "target": format(row.target, "f"),
        "shares": row.shares,
        "max_loss": format(row.max_loss, "f") if row.max_loss is not None else None,
        "orin_score": row.orin_score,
        "orin_expected_move_percent": (
            format(row.orin_expected_move_percent, "f")
            if row.orin_expected_move_percent is not None
            else None
        ),
        "checklist_score": row.checklist_score,
        "vesk_result": vesk,
        "luma_reasoning": row.luma_reasoning,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "approved_at": row.approved_at.isoformat() if row.approved_at else None,
        "order_id": row.order_id,
        "journal_plan_id": row.journal_plan_id,
    }


@router.get("/settings")
def read_settings(db: Session = Depends(get_db)) -> dict[str, Any]:
    settings = get_or_create_settings(db)
    return _settings_payload(settings, backtest_gate_status(db))


@router.put("/settings")
def put_settings(
    body: AgentSettingsUpdate,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        settings = update_settings(db, body.model_dump(exclude_unset=True))
    except AgentSettingsError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _settings_payload(settings, backtest_gate_status(db))


@router.post("/kill-switch")
def kill_switch(db: Session = Depends(get_db)) -> dict[str, Any]:
    settings = toggle_kill_switch(db)
    state = "armed" if settings.kill_switch else "cleared"
    log_event(
        db,
        cycle_id="human",
        agent="HUMAN",
        event_type="kill_switch",
        payload={
            "kill_switch": settings.kill_switch,
            "summary": f"Human {state} the kill switch",
            "details": [
                f"Kill switch is now {'ON' if settings.kill_switch else 'OFF'}",
                f"Agents enabled: {settings.enabled}",
            ],
        },
    )
    return _settings_payload(settings, backtest_gate_status(db))


@router.post("/run-cycle")
def post_run_cycle(
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
    provider: MarketDataProvider = Depends(get_market_data_provider),
    broker=Depends(get_paper_broker),
) -> dict[str, Any]:
    """Manually run one cycle. ``force`` bypasses market-hours skip for testing."""
    summary = run_cycle(
        db,
        provider,
        broker,
        earnings_provider=get_earnings_provider(),
        force=force,
    )
    return summary.model_dump(mode="json")


@router.get("/proposals")
def get_proposals(
    status: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    return [_proposal_payload(row) for row in list_proposals(db, status=status)]


@router.post("/proposals/{proposal_id}/approve")
def approve_proposal(
    proposal_id: int,
    db: Session = Depends(get_db),
    provider: MarketDataProvider = Depends(get_market_data_provider),
    broker=Depends(get_paper_broker),
) -> dict[str, Any]:
    proposal = db.get(Proposal, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal.status == "vetoed":
        raise HTTPException(
            status_code=409,
            detail="Cannot approve a VESK-vetoed proposal (vetoes are final)",
        )
    if proposal.status not in ("pending",):
        raise HTTPException(
            status_code=409,
            detail=f"Proposal status is {proposal.status}, not pending",
        )

    proposal.status = "approved"
    proposal.approved_at = datetime.now(timezone.utc)
    db.commit()
    log_event(
        db,
        cycle_id=proposal.cycle_id,
        agent="HUMAN",
        event_type="approval",
        symbol=proposal.symbol,
        proposal_id=proposal.id,
        payload=log_detail.human_approval("approve", proposal.symbol),
    )

    last_price = None
    try:
        snaps = provider.get_snapshots([proposal.symbol])
        snap = snaps.get(proposal.symbol)
        if snap is not None:
            last_price = snap.last_price
    except MarketDataError:
        last_price = None

    settings = get_or_create_settings(db)
    paper_url = (os.getenv("ALPACA_PAPER_URL") or PAPER_URL_REQUIRED).strip().rstrip("/")
    result = run_kira(
        db,
        broker,
        KiraInput(
            proposal_id=proposal.id,
            symbol=proposal.symbol,
            status="approved",
            entry=proposal.entry,
            stop=proposal.stop,
            target=proposal.target,
            shares=int(proposal.shares or 0),
            expires_at=proposal.expires_at,
            last_price=last_price,
            paper_url=paper_url,
            client_order_id=str(proposal.id),
        ),
        account_size=Decimal(str(broker.get_account().equity)),
        risk_percent=settings.risk_per_trade_percent,
    )
    log_event(
        db,
        cycle_id=proposal.cycle_id,
        agent="KIRA",
        event_type="execution",
        symbol=proposal.symbol,
        proposal_id=proposal.id,
        payload=log_detail.kira_execution(
            result.model_dump(mode="json"),
            proposal.symbol,
        ),
    )
    db.refresh(proposal)
    return {
        "proposal": _proposal_payload(proposal),
        "kira": result.model_dump(mode="json"),
    }


@router.post("/proposals/{proposal_id}/reject")
def reject_proposal(
    proposal_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    proposal = db.get(Proposal, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal.status == "vetoed":
        raise HTTPException(
            status_code=409,
            detail="Vetoed proposals cannot be approved or need rejection override",
        )
    if proposal.status not in ("pending", "approved"):
        raise HTTPException(
            status_code=409,
            detail=f"Proposal status is {proposal.status}",
        )
    proposal.status = "rejected"
    db.commit()
    log_event(
        db,
        cycle_id=proposal.cycle_id,
        agent="HUMAN",
        event_type="rejection",
        symbol=proposal.symbol,
        proposal_id=proposal.id,
        payload=log_detail.human_approval("reject", proposal.symbol),
    )
    return _proposal_payload(proposal)


@router.get("/events")
def get_events(
    agent: Optional[str] = Query(default=None),
    symbol: Optional[str] = Query(default=None),
    event_type: Optional[str] = Query(default=None),
    from_ts: Optional[datetime] = Query(default=None, alias="from"),
    to_ts: Optional[datetime] = Query(default=None, alias="to"),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    stmt = select(AgentEvent).order_by(AgentEvent.created_at.desc(), AgentEvent.id.desc())
    if agent:
        stmt = stmt.where(AgentEvent.agent == agent)
    if symbol:
        stmt = stmt.where(AgentEvent.symbol == symbol.upper())
    if event_type:
        stmt = stmt.where(AgentEvent.event_type == event_type)
    if from_ts is not None:
        stmt = stmt.where(AgentEvent.created_at >= from_ts)
    if to_ts is not None:
        stmt = stmt.where(AgentEvent.created_at <= to_ts)
    stmt = stmt.limit(limit)
    rows = list(db.scalars(stmt).all())
    out: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(row.payload or "{}")
        except json.JSONDecodeError:
            payload = {}
        out.append(
            {
                "id": row.id,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "cycle_id": row.cycle_id,
                "agent": row.agent,
                "event_type": row.event_type,
                "symbol": row.symbol,
                "proposal_id": row.proposal_id,
                "duration_ms": row.duration_ms,
                "payload": payload,
            }
        )
    return out


@router.post("/review/run")
def post_review(db: Session = Depends(get_db)) -> dict[str, Any]:
    report = run_dash(db)
    payload = report.model_dump(mode="json")
    row = save_review(db, payload)
    log_event(
        db,
        cycle_id="review",
        agent="DASH",
        event_type="review",
        payload={"review_id": row.id},
    )
    return {
        "id": row.id,
        "created_at": row.created_at.isoformat(),
        "report": payload,
    }


@router.get("/review/latest")
def get_latest_review(db: Session = Depends(get_db)) -> dict[str, Any]:
    row = latest_review(db)
    if row is None:
        raise HTTPException(status_code=404, detail="No review has been run yet")
    try:
        report = json.loads(row.report)
    except json.JSONDecodeError:
        report = {}
    return {
        "id": row.id,
        "created_at": row.created_at.isoformat(),
        "report": report,
    }
