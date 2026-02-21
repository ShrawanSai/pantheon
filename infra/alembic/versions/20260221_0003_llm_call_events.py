"""llm call events usage ledger

Revision ID: 20260221_0003
Revises: 20260221_0002
Create Date: 2026-02-21 19:40:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260221_0003"
down_revision: Union[str, Sequence[str], None] = "20260221_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_call_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("room_id", sa.String(length=64), nullable=True),
        sa.Column("direct_session_id", sa.String(length=64), nullable=True),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("turn_id", sa.String(length=64), nullable=True),
        sa.Column("step_id", sa.String(length=64), nullable=True),
        sa.Column("agent_id", sa.String(length=64), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model_alias", sa.String(length=32), nullable=False),
        sa.Column("provider_model", sa.String(length=128), nullable=False),
        sa.Column("input_tokens_fresh", sa.Integer(), nullable=False),
        sa.Column("input_tokens_cached", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("oe_tokens_computed", sa.Numeric(20, 4), nullable=False),
        sa.Column("provider_cost_usd", sa.Numeric(20, 8), nullable=False),
        sa.Column("credits_burned", sa.Numeric(20, 4), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("pricing_version", sa.String(length=32), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["turn_id"], ["turns.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["step_id"], ["turn_steps.id"], ondelete="SET NULL"),
    )

    op.create_index("idx_llm_call_events_user_created_at", "llm_call_events", ["user_id", "created_at"])
    op.create_index("idx_llm_call_events_session_created_at", "llm_call_events", ["session_id", "created_at"])
    op.create_index("idx_llm_call_events_turn_id", "llm_call_events", ["turn_id"])
    op.create_index("idx_llm_call_events_model_alias_created_at", "llm_call_events", ["model_alias", "created_at"])
    op.create_index("idx_llm_call_events_created_at", "llm_call_events", ["created_at"])
    op.create_index(
        "uq_llm_call_events_request_id",
        "llm_call_events",
        ["request_id"],
        unique=True,
        postgresql_where=sa.text("request_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_llm_call_events_request_id", table_name="llm_call_events")
    op.drop_index("idx_llm_call_events_created_at", table_name="llm_call_events")
    op.drop_index("idx_llm_call_events_model_alias_created_at", table_name="llm_call_events")
    op.drop_index("idx_llm_call_events_turn_id", table_name="llm_call_events")
    op.drop_index("idx_llm_call_events_session_created_at", table_name="llm_call_events")
    op.drop_index("idx_llm_call_events_user_created_at", table_name="llm_call_events")
    op.drop_table("llm_call_events")
