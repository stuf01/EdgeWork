"""KIRA — Executor. Paper bracket orders only after human approval."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.agents import PAPER_URL_REQUIRED
from app.agents.paper_client import PaperBroker, PaperTradingError
from app.agents.schemas import KiraInput, KiraOutput
from app.models import Proposal, TradePlan
from app.planner import calculate_plan

HALF_PERCENT = Decimal("0.005")
TWO = Decimal("2")


def run_kira(
    db: Session,
    broker: PaperBroker,
    body: KiraInput,
    *,
    account_size: Decimal,
    risk_percent: Decimal,
) -> KiraOutput:
    """Execute an approved proposal as a paper bracket order.

    KIRA never alters entry/stop/target/size beyond the proposal.
    """
    if body.paper_url != PAPER_URL_REQUIRED:
        return KiraOutput(
            executed=False,
            status="failed",
            reason=(
                f"Refusing non-paper URL. Required exactly {PAPER_URL_REQUIRED}."
            ),
        )

    if body.status != "approved":
        return KiraOutput(
            executed=False,
            status=body.status,
            reason="KIRA only acts on proposals approved by a human",
        )

    now = datetime.now(timezone.utc)
    if body.expires_at is not None:
        expires = body.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if now > expires:
            _mark_proposal(db, body.proposal_id, status="expired")
            return KiraOutput(
                executed=False,
                status="expired",
                reason="Proposal expired before execution",
            )

    # Price-drift / R:R re-check — expire rather than trade.
    if body.last_price is not None and body.entry > 0:
        drift = abs(body.last_price - body.entry) / body.entry
        if drift > HALF_PERCENT:
            _mark_proposal(db, body.proposal_id, status="expired")
            return KiraOutput(
                executed=False,
                status="expired",
                reason="Entry is more than 0.5% away from last price",
            )
    try:
        plan = calculate_plan(
            account_size,
            risk_percent,
            body.entry,
            body.stop,
            body.target,
        )
        if plan["risk_reward_ratio"] < TWO:
            _mark_proposal(db, body.proposal_id, status="expired")
            return KiraOutput(
                executed=False,
                status="expired",
                reason="Risk/reward fell below 2",
            )
    except ValueError as exc:
        _mark_proposal(db, body.proposal_id, status="expired")
        return KiraOutput(
            executed=False,
            status="expired",
            reason=f"Plan invalid at execution: {exc}",
        )

    client_order_id = body.client_order_id or str(body.proposal_id)
    try:
        existing = broker.get_order_by_client_id(client_order_id)
        if existing is not None:
            order = existing
        else:
            order = broker.submit_bracket_order(
                symbol=body.symbol,
                qty=body.shares,
                entry=body.entry,
                stop=body.stop,
                target=body.target,
                client_order_id=client_order_id,
            )
    except PaperTradingError as exc:
        _mark_proposal(db, body.proposal_id, status="failed")
        return KiraOutput(
            executed=False,
            status="failed",
            reason=str(exc),
        )

    journal_id = _ensure_journal_plan(
        db,
        proposal_id=body.proposal_id,
        symbol=body.symbol,
        entry=body.entry,
        stop=body.stop,
        target=body.target,
        shares=body.shares,
        account_size=account_size,
        risk_percent=risk_percent,
    )
    proposal = db.get(Proposal, body.proposal_id)
    if proposal is not None:
        proposal.status = "executed"
        proposal.order_id = order.id
        proposal.journal_plan_id = journal_id
        db.commit()

    return KiraOutput(
        executed=True,
        status="executed",
        order_id=order.id,
        journal_plan_id=journal_id,
    )


def _mark_proposal(db: Session, proposal_id: int, *, status: str) -> None:
    proposal = db.get(Proposal, proposal_id)
    if proposal is None:
        return
    proposal.status = status
    db.commit()


def _ensure_journal_plan(
    db: Session,
    *,
    proposal_id: int,
    symbol: str,
    entry: Decimal,
    stop: Decimal,
    target: Decimal,
    shares: int,
    account_size: Decimal,
    risk_percent: Decimal,
) -> Optional[int]:
    proposal = db.get(Proposal, proposal_id)
    if proposal is not None and proposal.journal_plan_id is not None:
        return proposal.journal_plan_id
    plan = calculate_plan(account_size, risk_percent, entry, stop, target)
    row = TradePlan(
        symbol=symbol.upper(),
        account_size=account_size,
        risk_percent=risk_percent,
        entry=entry,
        stop=stop,
        target=target,
        shares=shares,
        actual_risk=plan["actual_risk_dollars"],
        risk_reward=plan["risk_reward_ratio"],
        notes=f"agent-loop proposal {proposal_id}",
        status="open",
        is_paper=True,
        setup_tag="agent-loop",
        actual_entry=entry,
        shares_traded=shares,
        opened_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row.id
