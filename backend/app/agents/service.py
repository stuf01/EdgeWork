"""Persistence helpers for agent settings, proposals, and backtest gate."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.backtest_service import _unwrap_saved_summary, list_runs
from app.models import AgentReview, AgentSettings, Proposal


class AgentSettingsError(Exception):
    """Raised when settings cannot be updated."""


def get_or_create_settings(db: Session) -> AgentSettings:
    row = db.scalars(select(AgentSettings).order_by(AgentSettings.id.asc())).first()
    if row is not None:
        return row
    row = AgentSettings()
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def backtest_gate_status(db: Session) -> dict[str, Any]:
    """Return whether agents may be enabled and any weak-backtest warning."""
    runs = list_runs(db)
    if not runs:
        return {
            "allowed": False,
            "warning": None,
            "requires_confirmation": False,
            "message": "Enable requires at least one saved backtest run.",
            "latest_backtest_id": None,
            "latest_trade_count": 0,
            "latest_expectancy_r": None,
        }
    latest = runs[0]
    summary = _unwrap_saved_summary(json.loads(latest.summary))
    trades = int(summary.get("total_trades") or 0)
    exp_raw = summary.get("expectancy_r")
    expectancy = Decimal(str(exp_raw)) if exp_raw not in (None, "") else None
    weak = trades < 100 or (expectancy is not None and expectancy <= 0)
    settings = get_or_create_settings(db)
    if weak and not settings.backtest_weak_confirmed:
        return {
            "allowed": False,
            "warning": (
                "Latest backtest has fewer than 100 trades or expectancy ≤ 0. "
                "Confirm to proceed."
            ),
            "requires_confirmation": True,
            "message": "Weak backtest gate — confirmation required.",
            "latest_backtest_id": latest.id,
            "latest_trade_count": trades,
            "latest_expectancy_r": format(expectancy, "f") if expectancy is not None else None,
        }
    return {
        "allowed": True,
        "warning": (
            "Latest backtest is weak; you confirmed proceeding."
            if weak
            else None
        ),
        "requires_confirmation": False,
        "message": "Backtest gate passed.",
        "latest_backtest_id": latest.id,
        "latest_trade_count": trades,
        "latest_expectancy_r": format(expectancy, "f") if expectancy is not None else None,
    }


def update_settings(db: Session, updates: dict[str, Any]) -> AgentSettings:
    settings = get_or_create_settings(db)
    enabling = bool(updates.get("enabled", settings.enabled))
    if enabling and not settings.enabled:
        gate = backtest_gate_status(db)
        if not gate["allowed"]:
            if gate.get("requires_confirmation") and updates.get(
                "confirm_weak_backtest"
            ):
                settings.backtest_weak_confirmed = True
                db.commit()
                gate = backtest_gate_status(db)
            if not gate["allowed"]:
                raise AgentSettingsError(gate["message"])

    for key in (
        "enabled",
        "kill_switch",
        "max_open_positions",
        "max_trades_per_day",
        "proposal_ttl_minutes",
        "min_orin_score",
        "min_checklist_score",
        "checklist_id",
        "cycle_interval_minutes",
        "scheduler_enabled",
        "backtest_weak_confirmed",
    ):
        if key in updates and updates[key] is not None:
            setattr(settings, key, updates[key])
    if "daily_loss_limit_percent" in updates and updates["daily_loss_limit_percent"] is not None:
        settings.daily_loss_limit_percent = Decimal(
            str(updates["daily_loss_limit_percent"])
        )
    if "risk_per_trade_percent" in updates and updates["risk_per_trade_percent"] is not None:
        settings.risk_per_trade_percent = Decimal(
            str(updates["risk_per_trade_percent"])
        )
    db.commit()
    db.refresh(settings)
    return settings


def toggle_kill_switch(db: Session) -> AgentSettings:
    settings = get_or_create_settings(db)
    settings.kill_switch = not settings.kill_switch
    if settings.kill_switch:
        settings.enabled = False
    db.commit()
    db.refresh(settings)
    return settings


def list_proposals(
    db: Session,
    *,
    status: Optional[str] = None,
) -> list[Proposal]:
    stmt = select(Proposal).order_by(Proposal.created_at.desc(), Proposal.id.desc())
    if status:
        stmt = stmt.where(Proposal.status == status)
    return list(db.scalars(stmt).all())


def save_review(db: Session, report: dict[str, Any]) -> AgentReview:
    row = AgentReview(
        created_at=datetime.now(timezone.utc),
        report=json.dumps(report, default=str),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def latest_review(db: Session) -> Optional[AgentReview]:
    return db.scalars(
        select(AgentReview).order_by(AgentReview.created_at.desc(), AgentReview.id.desc())
    ).first()
