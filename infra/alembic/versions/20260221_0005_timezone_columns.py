"""normalize datetime columns to timestamptz

Revision ID: 20260221_0005
Revises: 20260221_0004
Create Date: 2026-02-21 22:40:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260221_0005"
down_revision: Union[str, Sequence[str], None] = "20260221_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _to_timestamptz(table: str, column: str) -> None:
    op.execute(
        sa.text(
            f'ALTER TABLE "{table}" '
            f'ALTER COLUMN "{column}" TYPE TIMESTAMP WITH TIME ZONE '
            f'USING "{column}" AT TIME ZONE \'UTC\''
        )
    )


def _to_timestamp(table: str, column: str) -> None:
    op.execute(
        sa.text(
            f'ALTER TABLE "{table}" '
            f'ALTER COLUMN "{column}" TYPE TIMESTAMP WITHOUT TIME ZONE '
            f'USING "{column}" AT TIME ZONE \'UTC\''
        )
    )


def upgrade() -> None:
    _to_timestamptz("users", "created_at")
    _to_timestamptz("users", "updated_at")

    _to_timestamptz("rooms", "deleted_at")
    _to_timestamptz("rooms", "created_at")
    _to_timestamptz("rooms", "updated_at")

    _to_timestamptz("room_agents", "created_at")

    _to_timestamptz("sessions", "deleted_at")
    _to_timestamptz("sessions", "created_at")

    _to_timestamptz("turns", "created_at")
    _to_timestamptz("messages", "created_at")
    _to_timestamptz("session_summaries", "created_at")
    _to_timestamptz("turn_context_audit", "created_at")


def downgrade() -> None:
    _to_timestamp("turn_context_audit", "created_at")
    _to_timestamp("session_summaries", "created_at")
    _to_timestamp("messages", "created_at")
    _to_timestamp("turns", "created_at")

    _to_timestamp("sessions", "created_at")
    _to_timestamp("sessions", "deleted_at")

    _to_timestamp("room_agents", "created_at")

    _to_timestamp("rooms", "updated_at")
    _to_timestamp("rooms", "created_at")
    _to_timestamp("rooms", "deleted_at")

    _to_timestamp("users", "updated_at")
    _to_timestamp("users", "created_at")
