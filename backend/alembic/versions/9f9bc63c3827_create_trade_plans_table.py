"""create trade_plans table

Revision ID: 9f9bc63c3827
Revises:
Create Date: 2026-10-30 10:50:43.686852

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.models import DecimalString

# revision identifiers, used by Alembic.
revision: str = "9f9bc63c3827"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "trade_plans",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("account_size", DecimalString(), nullable=False),
        sa.Column("risk_percent", DecimalString(), nullable=False),
        sa.Column("entry", DecimalString(), nullable=False),
        sa.Column("stop", DecimalString(), nullable=False),
        sa.Column("target", DecimalString(), nullable=False),
        sa.Column("shares", sa.Integer(), nullable=False),
        sa.Column("actual_risk", DecimalString(), nullable=False),
        sa.Column("risk_reward", DecimalString(), nullable=False),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("trade_plans")
