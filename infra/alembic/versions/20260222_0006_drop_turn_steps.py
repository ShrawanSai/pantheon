"""drop unused turn_steps table and step_id foreign key

Revision ID: 20260222_0006
Revises: 20260221_0005
Create Date: 2026-02-22 11:05:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260222_0006"
down_revision: Union[str, Sequence[str], None] = "20260221_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("llm_call_events_step_id_fkey", "llm_call_events", type_="foreignkey")
    op.drop_index("ix_turn_steps_turn_id", table_name="turn_steps")
    op.drop_table("turn_steps")


def downgrade() -> None:
    op.create_table(
        "turn_steps",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("turn_id", sa.String(length=64), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("agent_name", sa.String(length=120), nullable=False),
        sa.Column("model_alias", sa.String(length=64), nullable=False),
        sa.Column("output_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'success'")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["turn_id"], ["turns.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("turn_id", "step_index", name="uq_turn_steps_turn_step_index"),
    )
    op.create_index("ix_turn_steps_turn_id", "turn_steps", ["turn_id"])
    op.create_foreign_key(
        "llm_call_events_step_id_fkey",
        "llm_call_events",
        "turn_steps",
        ["step_id"],
        ["id"],
        ondelete="SET NULL",
    )
