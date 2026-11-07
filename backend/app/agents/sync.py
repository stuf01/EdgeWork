"""Sync open paper orders into journal entries."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.events import log_event
from app.agents.paper_client import PaperBroker, PaperTradingError
from app.models import Proposal, TradePlan


def sync_open_orders(db: Session, broker: PaperBroker) -> int:
    """Update executed proposals / journal rows from broker order status.

    Returns number of proposals touched.
    """
    proposals = list(
        db.scalars(
            select(Proposal).where(
                Proposal.status == "executed",
                Proposal.order_id.is_not(None),
            )
        )
    )
    touched = 0
    for proposal in proposals:
        if not proposal.order_id:
            continue
        try:
            order = broker.get_order(proposal.order_id)
        except PaperTradingError:
            continue
        plan = (
            db.get(TradePlan, proposal.journal_plan_id)
            if proposal.journal_plan_id
            else None
        )
        if order.status == "filled" and plan is not None and plan.status == "open":
            # Entry filled — leave open until legs close; mark entry if needed.
            if plan.actual_entry is None and order.filled_avg_price is not None:
                plan.actual_entry = order.filled_avg_price
                plan.shares_traded = int(order.filled_qty or plan.shares or 0)
                plan.opened_at = plan.opened_at or datetime.now(timezone.utc)
                touched += 1
        if order.status in ("canceled", "cancelled", "expired", "rejected"):
            if plan is not None and plan.status == "open":
                plan.status = "skipped"
                plan.lessons = f"Order {order.status}"
                touched += 1
            proposal.status = "cancelled"
            touched += 1
            log_event(
                db,
                cycle_id=proposal.cycle_id,
                agent="KIRA",
                event_type="order_sync",
                symbol=proposal.symbol,
                proposal_id=proposal.id,
                payload={"order_status": order.status},
                commit=False,
            )
    if touched:
        db.commit()
    return touched
