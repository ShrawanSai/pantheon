"""core week2 schema

Revision ID: 20260221_0002
Revises: 20260221_0001
Create Date: 2026-02-21 13:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260221_0002"
down_revision: Union[str, Sequence[str], None] = "20260221_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )

    op.create_table(
        "rooms",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("owner_user_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("goal", sa.Text(), nullable=True),
        sa.Column("current_mode", sa.String(length=32), nullable=False),
        sa.Column("pending_mode", sa.String(length=32), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_rooms_owner_user_id", "rooms", ["owner_user_id"])

    op.create_table(
        "room_agents",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("room_id", sa.String(length=64), nullable=False),
        sa.Column("agent_key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("model_alias", sa.String(length=64), nullable=False),
        sa.Column("role_prompt", sa.Text(), nullable=False),
        sa.Column("tool_permissions_json", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("room_id", "agent_key", name="uq_room_agents_room_agent_key"),
    )
    op.create_index("ix_room_agents_room_id", "room_agents", ["room_id"])

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("room_id", sa.String(length=64), nullable=False),
        sa.Column("started_by_user_id", sa.String(length=64), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["started_by_user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_sessions_room_id", "sessions", ["room_id"])

    op.create_table(
        "turns",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("user_input", sa.Text(), nullable=False),
        sa.Column("assistant_output", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'completed'")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("session_id", "turn_index", name="uq_turns_session_turn_index"),
    )
    op.create_index("ix_turns_session_id", "turns", ["session_id"])

    op.create_table(
        "turn_steps",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("turn_id", sa.String(length=64), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("agent_name", sa.String(length=120), nullable=False),
        sa.Column("model_alias", sa.String(length=64), nullable=False),
        sa.Column("output_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'success'")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["turn_id"], ["turns.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("turn_id", "step_index", name="uq_turn_steps_turn_step_index"),
    )
    op.create_index("ix_turn_steps_turn_id", "turn_steps", ["turn_id"])

    op.create_table(
        "messages",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("turn_id", sa.String(length=64), nullable=True),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("agent_name", sa.String(length=120), nullable=True),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["turn_id"], ["turns.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_messages_session_id", "messages", ["session_id"])
    op.create_index("ix_messages_turn_id", "messages", ["turn_id"])


def downgrade() -> None:
    op.drop_index("ix_messages_turn_id", table_name="messages")
    op.drop_index("ix_messages_session_id", table_name="messages")
    op.drop_table("messages")

    op.drop_index("ix_turn_steps_turn_id", table_name="turn_steps")
    op.drop_table("turn_steps")

    op.drop_index("ix_turns_session_id", table_name="turns")
    op.drop_table("turns")

    op.drop_index("ix_sessions_room_id", table_name="sessions")
    op.drop_table("sessions")

    op.drop_index("ix_room_agents_room_id", table_name="room_agents")
    op.drop_table("room_agents")

    op.drop_index("ix_rooms_owner_user_id", table_name="rooms")
    op.drop_table("rooms")

    op.drop_table("users")
