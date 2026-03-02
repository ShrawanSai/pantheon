"""add name column to sessions

Revision ID: 20260302_0019
Revises: 20260223_0018
Create Date: 2026-03-02 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260302_0019"
down_revision: Union[str, Sequence[str], None] = "188056e6ae7f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.add_column(sa.Column("name", sa.String(length=200), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.drop_column("name")
