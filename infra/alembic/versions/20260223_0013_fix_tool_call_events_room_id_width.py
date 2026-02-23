"""widen tool_call_events.room_id to match id width convention

Revision ID: 20260223_0013
Revises: 20260222_0012
Create Date: 2026-02-23 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260223_0013"
down_revision: Union[str, Sequence[str], None] = "20260222_0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("tool_call_events") as batch_op:
        batch_op.alter_column(
            "room_id",
            existing_type=sa.String(length=36),
            type_=sa.String(length=64),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("tool_call_events") as batch_op:
        batch_op.alter_column(
            "room_id",
            existing_type=sa.String(length=64),
            type_=sa.String(length=36),
            existing_nullable=True,
        )
