"""add agent pipeline tables

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-11-06 20:50:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("kill_switch", sa.Boolean(), server_default="0", nullable=False),
        sa.Column(
            "max_open_positions", sa.Integer(), server_default="3", nullable=False
        ),
        sa.Column(
            "max_trades_per_day", sa.Integer(), server_default="3", nullable=False
        ),
        sa.Column(
            "daily_loss_limit_percent",
            sa.String(),
            server_default="3",
            nullable=False,
        ),
        sa.Column(
            "risk_per_trade_percent",
            sa.String(),
            server_default="1",
            nullable=False,
        ),
        sa.Column(
            "proposal_ttl_minutes", sa.Integer(), server_default="10", nullable=False
        ),
        sa.Column("min_orin_score", sa.Integer(), server_default="60", nullable=False),
        sa.Column(
            "min_checklist_score", sa.Integer(), server_default="70", nullable=False
        ),
        sa.Column("checklist_id", sa.Integer(), nullable=True),
        sa.Column(
            "cycle_interval_minutes", sa.Integer(), server_default="5", nullable=False
        ),
        sa.Column(
            "scheduler_enabled", sa.Boolean(), server_default="0", nullable=False
        ),
        sa.Column(
            "backtest_weak_confirmed",
            sa.Boolean(),
            server_default="0",
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["checklist_id"],
            ["checklists.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "proposals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cycle_id", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("entry", sa.String(), nullable=False),
        sa.Column("stop", sa.String(), nullable=False),
        sa.Column("target", sa.String(), nullable=False),
        sa.Column("shares", sa.Integer(), nullable=True),
        sa.Column("max_loss", sa.String(), nullable=True),
        sa.Column("orin_score", sa.Integer(), nullable=True),
        sa.Column("orin_expected_move_percent", sa.String(), nullable=True),
        sa.Column("checklist_score", sa.Integer(), nullable=True),
        sa.Column("vesk_result", sa.Text(), nullable=True),
        sa.Column("luma_reasoning", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("order_id", sa.String(length=128), nullable=True),
        sa.Column("journal_plan_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["journal_plan_id"],
            ["trade_plans.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "agent_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cycle_id", sa.String(length=64), nullable=False),
        sa.Column("agent", sa.String(length=16), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=True),
        sa.Column("proposal_id", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("payload", sa.Text(), server_default="{}", nullable=False),
        sa.ForeignKeyConstraint(
            ["proposal_id"],
            ["proposals.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("agent_events", schema=None) as batch_op:
        batch_op.create_index("ix_agent_events_cycle_id", ["cycle_id"], unique=False)

    op.create_table(
        "agent_reviews",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("report", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("agent_reviews")
    with op.batch_alter_table("agent_events", schema=None) as batch_op:
        batch_op.drop_index("ix_agent_events_cycle_id")
    op.drop_table("agent_events")
    op.drop_table("proposals")
    op.drop_table("agent_settings")
