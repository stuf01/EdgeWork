"""ORM models for the trade planner / journal / checklists."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    TypeDecorator,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DecimalString(TypeDecorator):
    """Store Decimal values as TEXT so SQLite never coerces them to float."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, Decimal):
            value = Decimal(str(value))
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return Decimal(value)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


PLAN_STATUSES = ("planned", "open", "closed", "skipped")
EXIT_REASONS = ("target_hit", "stop_hit", "manual_exit", "other")


class TradePlan(Base):
    """A saved long-side trade plan / journal entry."""

    __tablename__ = "trade_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    account_size: Mapped[Decimal] = mapped_column(DecimalString, nullable=False)
    risk_percent: Mapped[Decimal] = mapped_column(DecimalString, nullable=False)
    entry: Mapped[Decimal] = mapped_column(DecimalString, nullable=False)
    stop: Mapped[Decimal] = mapped_column(DecimalString, nullable=False)
    target: Mapped[Decimal] = mapped_column(DecimalString, nullable=False)
    shares: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_risk: Mapped[Decimal] = mapped_column(DecimalString, nullable=False)
    risk_reward: Mapped[Decimal] = mapped_column(DecimalString, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="planned",
        server_default="planned",
    )
    is_paper: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="1",
    )
    setup_tag: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    actual_entry: Mapped[Optional[Decimal]] = mapped_column(
        DecimalString,
        nullable=True,
    )
    actual_exit: Mapped[Optional[Decimal]] = mapped_column(
        DecimalString,
        nullable=True,
    )
    shares_traded: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    exit_reason: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    opened_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    lessons: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    checklist_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    checklist_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("checklists.id", ondelete="SET NULL"),
        nullable=True,
    )


class WatchlistItem(Base):
    """A symbol tracked for the scanner."""

    __tablename__ = "watchlist_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        nullable=False,
    )
    notes: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)


class Checklist(Base):
    """Named set of setup rules."""

    __tablename__ = "checklists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        nullable=False,
    )
    rules: Mapped[list["ChecklistRule"]] = relationship(
        back_populates="checklist",
        cascade="all, delete-orphan",
        order_by="ChecklistRule.position",
    )


class ChecklistRule(Base):
    """One rule inside a checklist."""

    __tablename__ = "checklist_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    checklist_id: Mapped[int] = mapped_column(
        ForeignKey("checklists.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(64), nullable=False)
    operator: Mapped[str] = mapped_column(String(8), nullable=False)
    threshold: Mapped[Optional[Decimal]] = mapped_column(DecimalString, nullable=True)
    required: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
    )
    checklist: Mapped[Checklist] = relationship(back_populates="rules")


class BacktestRun(Base):
    """Saved backtest run with parameters, summary, and trades as JSON."""

    __tablename__ = "backtest_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        nullable=False,
    )
    name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    parameters: Mapped[str] = mapped_column(Text, nullable=False)
    symbols: Mapped[str] = mapped_column(Text, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    trades: Mapped[str] = mapped_column(Text, nullable=False)


AGENT_NAMES = ("NOVA", "ORIN", "VESK", "LUMA", "KIRA", "DASH", "SYSTEM", "HUMAN")
PROPOSAL_STATUSES = (
    "pending",
    "approved",
    "rejected",
    "expired",
    "vetoed",
    "executed",
    "failed",
    "cancelled",
)


class AgentSettings(Base):
    """Single-row configuration for the paper agent loop."""

    __tablename__ = "agent_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    kill_switch: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    max_open_positions: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default="3"
    )
    max_trades_per_day: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default="3"
    )
    daily_loss_limit_percent: Mapped[Decimal] = mapped_column(
        DecimalString, nullable=False, default=Decimal("3"), server_default="3"
    )
    risk_per_trade_percent: Mapped[Decimal] = mapped_column(
        DecimalString, nullable=False, default=Decimal("1"), server_default="1"
    )
    proposal_ttl_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=10, server_default="10"
    )
    min_orin_score: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60, server_default="60"
    )
    min_checklist_score: Mapped[int] = mapped_column(
        Integer, nullable=False, default=70, server_default="70"
    )
    checklist_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("checklists.id", ondelete="SET NULL"),
        nullable=True,
    )
    cycle_interval_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=5, server_default="5"
    )
    scheduler_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    backtest_weak_confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )


class Proposal(Base):
    """A candidate trade routed through the agent loop."""

    __tablename__ = "proposals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        nullable=False,
    )
    cycle_id: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    entry: Mapped[Decimal] = mapped_column(DecimalString, nullable=False)
    stop: Mapped[Decimal] = mapped_column(DecimalString, nullable=False)
    target: Mapped[Decimal] = mapped_column(DecimalString, nullable=False)
    shares: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_loss: Mapped[Optional[Decimal]] = mapped_column(DecimalString, nullable=True)
    orin_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    orin_expected_move_percent: Mapped[Optional[Decimal]] = mapped_column(
        DecimalString, nullable=True
    )
    checklist_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    vesk_result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    luma_reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    order_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    journal_plan_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("trade_plans.id", ondelete="SET NULL"),
        nullable=True,
    )


class AgentEvent(Base):
    """Append-only event log for the agent pipeline."""

    __tablename__ = "agent_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        nullable=False,
    )
    cycle_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    agent: Mapped[str] = mapped_column(String(16), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    proposal_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("proposals.id", ondelete="SET NULL"),
        nullable=True,
    )
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class AgentReview(Base):
    """Persisted DASH review report."""

    __tablename__ = "agent_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utc_now,
        nullable=False,
    )
    report: Mapped[str] = mapped_column(Text, nullable=False)
