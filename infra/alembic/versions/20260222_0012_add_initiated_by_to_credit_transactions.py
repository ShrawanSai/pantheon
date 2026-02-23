"""add initiated_by to credit transactions

Revision ID: 20260222_0012
Revises: 20260222_0011
Create Date: 2026-02-23 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260222_0012"
down_revision: Union[str, Sequence[str], None] = "20260222_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "credit_transactions",
        sa.Column("initiated_by", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("credit_transactions", "initiated_by")
