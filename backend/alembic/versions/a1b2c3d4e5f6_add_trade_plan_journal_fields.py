"""add trade plan journal fields

Revision ID: a1b2c3d4e5f6
Revises: 2d375de1169c
Create Date: 2026-10-30 15:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.models import DecimalString

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "2d375de1169c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema with journal columns and defaults for existing rows."""
    with op.batch_alter_table("trade_plans") as batch_op:
        batch_op.add_column(
            sa.Column(
                "status",
                sa.String(length=16),
                nullable=False,
                server_default="planned",
            )
        )
        batch_op.add_column(
            sa.Column(
                "is_paper",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("1"),
            )
        )
        batch_op.add_column(sa.Column("setup_tag", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("actual_entry", DecimalString(), nullable=True))
        batch_op.add_column(sa.Column("actual_exit", DecimalString(), nullable=True))
        batch_op.add_column(sa.Column("shares_traded", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("exit_reason", sa.String(length=32), nullable=True)
        )
        batch_op.add_column(
            sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(sa.Column("lessons", sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove journal columns."""
    with op.batch_alter_table("trade_plans") as batch_op:
        batch_op.drop_column("lessons")
        batch_op.drop_column("closed_at")
        batch_op.drop_column("opened_at")
        batch_op.drop_column("exit_reason")
        batch_op.drop_column("shares_traded")
        batch_op.drop_column("actual_exit")
        batch_op.drop_column("actual_entry")
        batch_op.drop_column("setup_tag")
        batch_op.drop_column("is_paper")
        batch_op.drop_column("status")
