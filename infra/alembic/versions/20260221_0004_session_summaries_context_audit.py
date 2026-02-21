"""session summaries and context audit tables

Revision ID: 20260221_0004
Revises: 20260221_0003
Create Date: 2026-02-21 23:10:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260221_0004"
down_revision: Union[str, Sequence[str], None] = "20260221_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "session_summaries",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("from_message_id", sa.String(length=64), nullable=True),
        sa.Column("to_message_id", sa.String(length=64), nullable=True),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("key_facts_json", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("open_questions_json", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("decisions_json", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("action_items_json", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_session_summaries_session_id", "session_summaries", ["session_id"])

    op.create_table(
        "turn_context_audit",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("turn_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("model_alias", sa.String(length=64), nullable=False),
        sa.Column("model_context_limit", sa.Integer(), nullable=False),
        sa.Column("input_budget", sa.Integer(), nullable=False),
        sa.Column("estimated_input_tokens_before", sa.Integer(), nullable=False),
        sa.Column("estimated_input_tokens_after_summary", sa.Integer(), nullable=False),
        sa.Column("estimated_input_tokens_after_prune", sa.Integer(), nullable=False),
        sa.Column("summary_triggered", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("prune_triggered", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("overflow_rejected", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("output_reserve", sa.Integer(), nullable=False),
        sa.Column("overhead_reserve", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["turn_id"], ["turns.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_turn_context_audit_session_id", "turn_context_audit", ["session_id"])
    op.create_index("ix_turn_context_audit_turn_id", "turn_context_audit", ["turn_id"])


def downgrade() -> None:
    op.drop_index("ix_turn_context_audit_turn_id", table_name="turn_context_audit")
    op.drop_index("ix_turn_context_audit_session_id", table_name="turn_context_audit")
    op.drop_table("turn_context_audit")

    op.drop_index("ix_session_summaries_session_id", table_name="session_summaries")
    op.drop_table("session_summaries")

