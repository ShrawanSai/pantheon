"""align tool_call_events.status default with ORM

Revision ID: 20260222_0008
Revises: 20260222_0007
Create Date: 2026-02-22 23:55:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260222_0008"
down_revision: Union[str, Sequence[str], None] = "20260222_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "tool_call_events",
        "status",
        existing_type=sa.String(length=16),
        server_default=sa.text("'success'"),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "tool_call_events",
        "status",
        existing_type=sa.String(length=16),
        server_default=None,
        existing_nullable=False,
    )

