"""create tool_call_events table

Revision ID: 20260222_0007
Revises: 20260222_0006
Create Date: 2026-02-22 23:30:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260222_0007"
down_revision: Union[str, Sequence[str], None] = "20260222_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tool_call_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("room_id", sa.String(length=36), nullable=True),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("turn_id", sa.String(length=36), nullable=False),
        sa.Column("agent_key", sa.String(length=64), nullable=True),
        sa.Column("tool_name", sa.String(length=64), nullable=False),
        sa.Column("tool_input_json", sa.Text(), nullable=False),
        sa.Column("tool_output_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("credits_charged", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["turn_id"], ["turns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tool_call_events_turn_id", "tool_call_events", ["turn_id"])
    op.create_index("ix_tool_call_events_session_id", "tool_call_events", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_tool_call_events_session_id", table_name="tool_call_events")
    op.drop_index("ix_tool_call_events_turn_id", table_name="tool_call_events")
    op.drop_table("tool_call_events")

