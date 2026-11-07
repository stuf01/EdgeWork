"""add checklists and plan checklist fields

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-10-30 15:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.models import DecimalString

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create checklist tables and link columns on trade_plans."""
    op.create_table(
        "checklists",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "checklist_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("checklist_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=256), nullable=False),
        sa.Column("rule_type", sa.String(length=64), nullable=False),
        sa.Column("operator", sa.String(length=8), nullable=False),
        sa.Column("threshold", DecimalString(), nullable=True),
        sa.Column(
            "required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.ForeignKeyConstraint(
            ["checklist_id"],
            ["checklists.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("trade_plans") as batch_op:
        batch_op.add_column(sa.Column("checklist_score", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("checklist_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_trade_plans_checklist_id",
            "checklists",
            ["checklist_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    """Drop checklist link and tables."""
    with op.batch_alter_table("trade_plans") as batch_op:
        batch_op.drop_constraint("fk_trade_plans_checklist_id", type_="foreignkey")
        batch_op.drop_column("checklist_id")
        batch_op.drop_column("checklist_score")
    op.drop_table("checklist_rules")
    op.drop_table("checklists")
