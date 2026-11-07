"""Database access helpers for trade plans and watchlist."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.checklist import (
    ALLOWED_OPERATORS,
    RULE_REGISTRY,
    default_breakout_rules,
)
from app.journal import ClosedTrade, realized_pnl, r_multiple
from app.models import (
    EXIT_REASONS,
    PLAN_STATUSES,
    Checklist,
    ChecklistRule,
    TradePlan,
    WatchlistItem,
)
from app.planner import calculate_plan


class DuplicateWatchlistSymbolError(Exception):
    """Raised when adding a symbol that is already on the watchlist."""


class PlanUpdateError(Exception):
    """Raised when a plan update fails validation."""


class ChecklistValidationError(Exception):
    """Raised when checklist or rule input is invalid."""


def create_plan(
    db: Session,
    *,
    symbol: str,
    account_size: Decimal,
    risk_percent: Decimal,
    entry: Decimal,
    stop: Decimal,
    target: Decimal,
    notes: Optional[str] = None,
    setup_tag: Optional[str] = None,
    is_paper: bool = True,
    checklist_id: Optional[int] = None,
    checklist_score: Optional[int] = None,
) -> TradePlan:
    """Calculate a plan and persist it."""
    result = calculate_plan(account_size, risk_percent, entry, stop, target)
    plan = TradePlan(
        symbol=symbol.upper(),
        account_size=account_size,
        risk_percent=risk_percent,
        entry=entry,
        stop=stop,
        target=target,
        shares=result["shares"],
        actual_risk=result["actual_risk_dollars"],
        risk_reward=result["risk_reward_ratio"],
        notes=notes,
        setup_tag=setup_tag,
        is_paper=is_paper,
        status="planned",
        checklist_id=checklist_id,
        checklist_score=checklist_score,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def list_plans(db: Session) -> Sequence[TradePlan]:
    """Return all plans, newest first."""
    stmt = select(TradePlan).order_by(TradePlan.created_at.desc(), TradePlan.id.desc())
    return db.scalars(stmt).all()


def get_plan(db: Session, plan_id: int) -> Optional[TradePlan]:
    """Return a plan by id or None."""
    return db.get(TradePlan, plan_id)


def update_plan(
    db: Session,
    plan: TradePlan,
    *,
    status: Optional[str] = None,
    notes: Optional[str] = None,
    setup_tag: Optional[str] = None,
    is_paper: Optional[bool] = None,
    actual_entry: Optional[Decimal] = None,
    actual_exit: Optional[Decimal] = None,
    shares_traded: Optional[int] = None,
    exit_reason: Optional[str] = None,
    lessons: Optional[str] = None,
    fields_set: Optional[set[str]] = None,
) -> TradePlan:
    """Apply a partial journal update with status transition rules."""
    set_fields = fields_set or set()

    if status is not None:
        if status not in PLAN_STATUSES:
            raise PlanUpdateError(f"status must be one of {', '.join(PLAN_STATUSES)}")
    if exit_reason is not None and exit_reason not in EXIT_REASONS:
        raise PlanUpdateError(
            f"exit_reason must be one of {', '.join(EXIT_REASONS)}"
        )

    previous_status = plan.status

    if "notes" in set_fields:
        plan.notes = notes
    if "setup_tag" in set_fields:
        plan.setup_tag = setup_tag
    if "is_paper" in set_fields and is_paper is not None:
        plan.is_paper = is_paper
    if "actual_entry" in set_fields:
        plan.actual_entry = actual_entry
    if "actual_exit" in set_fields:
        plan.actual_exit = actual_exit
    if "shares_traded" in set_fields:
        plan.shares_traded = shares_traded
    if "exit_reason" in set_fields:
        plan.exit_reason = exit_reason
    if "lessons" in set_fields:
        plan.lessons = lessons

    new_status = status if status is not None else plan.status

    if new_status == "closed":
        if plan.actual_entry is None or plan.actual_exit is None or plan.shares_traded is None:
            raise PlanUpdateError(
                "closed trades require actual_entry, actual_exit, and shares_traded"
            )

    now = datetime.now(timezone.utc)
    if status is not None and status != previous_status:
        plan.status = status
        if status == "open" and plan.opened_at is None:
            plan.opened_at = now
        if status == "closed" and plan.closed_at is None:
            plan.closed_at = now
    elif status is not None:
        plan.status = status

    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def delete_plan(db: Session, plan_id: int) -> bool:
    """Delete a plan by id. Returns True if deleted, False if not found."""
    plan = db.get(TradePlan, plan_id)
    if plan is None:
        return False
    db.delete(plan)
    db.commit()
    return True


def list_closed_trades(
    db: Session,
    *,
    is_paper: Optional[bool] = None,
    setup_tag: Optional[str] = None,
    from_dt: Optional[datetime] = None,
    to_dt: Optional[datetime] = None,
) -> list[TradePlan]:
    """Return closed plans matching optional journal filters."""
    stmt = select(TradePlan).where(TradePlan.status == "closed")
    if is_paper is not None:
        stmt = stmt.where(TradePlan.is_paper.is_(is_paper))
    if setup_tag is not None:
        cleaned = setup_tag.strip()
        if cleaned.lower() == "untagged":
            stmt = stmt.where(
                (TradePlan.setup_tag.is_(None)) | (TradePlan.setup_tag == "")
            )
        else:
            stmt = stmt.where(TradePlan.setup_tag == cleaned)
    if from_dt is not None:
        stmt = stmt.where(TradePlan.closed_at >= from_dt)
    if to_dt is not None:
        stmt = stmt.where(TradePlan.closed_at <= to_dt)
    stmt = stmt.order_by(TradePlan.closed_at.asc(), TradePlan.id.asc())
    return list(db.scalars(stmt).all())


def plan_to_closed_trade(plan: TradePlan) -> ClosedTrade:
    """Map a closed ORM plan to journal ClosedTrade."""
    if (
        plan.actual_entry is None
        or plan.actual_exit is None
        or plan.shares_traded is None
        or plan.closed_at is None
    ):
        raise ValueError("plan is missing closed-trade fields")
    return ClosedTrade(
        actual_entry=plan.actual_entry,
        actual_exit=plan.actual_exit,
        shares_traded=plan.shares_traded,
        actual_risk=plan.actual_risk,
        setup_tag=plan.setup_tag,
        closed_at=plan.closed_at,
        checklist_score=plan.checklist_score,
    )


def enrich_plan_response_fields(plan: TradePlan) -> dict:
    """Extra computed fields for TradePlanResponse."""
    pnl = None
    r_val = None
    if (
        plan.status == "closed"
        and plan.actual_entry is not None
        and plan.actual_exit is not None
        and plan.shares_traded is not None
    ):
        pnl = realized_pnl(plan.actual_entry, plan.actual_exit, plan.shares_traded)
        r_val = r_multiple(pnl, plan.actual_risk)
    return {"realized_pnl": pnl, "r_multiple": r_val}


def list_watchlist(db: Session) -> Sequence[WatchlistItem]:
    """Return watchlist items, newest first."""
    stmt = select(WatchlistItem).order_by(
        WatchlistItem.added_at.desc(),
        WatchlistItem.id.desc(),
    )
    return db.scalars(stmt).all()


def add_watchlist_item(
    db: Session,
    *,
    symbol: str,
    notes: Optional[str] = None,
) -> WatchlistItem:
    """Add a symbol to the watchlist. Raises DuplicateWatchlistSymbolError."""
    item = WatchlistItem(symbol=symbol.upper(), notes=notes)
    db.add(item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateWatchlistSymbolError(
            f"Symbol {symbol.upper()} is already on the watchlist"
        ) from exc
    db.refresh(item)
    return item


def delete_watchlist_item(db: Session, symbol: str) -> bool:
    """Delete a watchlist item by symbol. Returns True if deleted."""
    stmt = select(WatchlistItem).where(WatchlistItem.symbol == symbol.upper())
    item = db.scalars(stmt).first()
    if item is None:
        return False
    db.delete(item)
    db.commit()
    return True


def validate_rule_fields(
    *,
    rule_type: str,
    operator: str,
) -> None:
    if rule_type not in RULE_REGISTRY:
        raise ChecklistValidationError(
            f"Unknown rule_type '{rule_type}'. "
            f"Allowed: {', '.join(sorted(RULE_REGISTRY))}"
        )
    if operator not in ALLOWED_OPERATORS:
        raise ChecklistValidationError(
            f"Invalid operator '{operator}'. "
            f"Allowed: {', '.join(ALLOWED_OPERATORS)}"
        )


def list_checklists(db: Session) -> Sequence[Checklist]:
    stmt = select(Checklist).order_by(Checklist.created_at.asc(), Checklist.id.asc())
    return db.scalars(stmt).all()


def get_checklist(db: Session, checklist_id: int) -> Optional[Checklist]:
    return db.get(Checklist, checklist_id)


def create_checklist(
    db: Session,
    *,
    name: str,
    description: Optional[str],
    rules: list[dict],
) -> Checklist:
    cleaned = name.strip()
    if not cleaned:
        raise ChecklistValidationError("name must not be empty")
    checklist = Checklist(name=cleaned, description=description)
    for index, rule in enumerate(rules):
        validate_rule_fields(
            rule_type=rule["rule_type"],
            operator=rule["operator"],
        )
        checklist.rules.append(
            ChecklistRule(
                position=rule.get("position", index),
                label=rule["label"],
                rule_type=rule["rule_type"],
                operator=rule["operator"],
                threshold=rule.get("threshold"),
                required=bool(rule.get("required", False)),
            )
        )
    db.add(checklist)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ChecklistValidationError(
            f"Checklist name '{cleaned}' already exists"
        ) from exc
    db.refresh(checklist)
    return checklist


def replace_checklist(
    db: Session,
    checklist: Checklist,
    *,
    name: str,
    description: Optional[str],
    rules: list[dict],
) -> Checklist:
    cleaned = name.strip()
    if not cleaned:
        raise ChecklistValidationError("name must not be empty")
    checklist.name = cleaned
    checklist.description = description
    checklist.rules.clear()
    db.flush()
    for index, rule in enumerate(rules):
        validate_rule_fields(
            rule_type=rule["rule_type"],
            operator=rule["operator"],
        )
        checklist.rules.append(
            ChecklistRule(
                position=rule.get("position", index),
                label=rule["label"],
                rule_type=rule["rule_type"],
                operator=rule["operator"],
                threshold=rule.get("threshold"),
                required=bool(rule.get("required", False)),
            )
        )
    db.add(checklist)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ChecklistValidationError(
            f"Checklist name '{cleaned}' already exists"
        ) from exc
    db.refresh(checklist)
    return checklist


def delete_checklist(db: Session, checklist_id: int) -> bool:
    checklist = db.get(Checklist, checklist_id)
    if checklist is None:
        return False
    db.delete(checklist)
    db.commit()
    return True


def ensure_default_checklist(db: Session) -> None:
    """Seed Breakout basics if no checklists exist."""
    existing = db.scalars(select(Checklist).limit(1)).first()
    if existing is not None:
        return
    create_checklist(
        db,
        name="Breakout basics",
        description="Default breakout setup checklist",
        rules=default_breakout_rules(),
    )
