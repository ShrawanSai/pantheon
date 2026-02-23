"""add standalone agent session scope columns

Revision ID: 20260223_0016
Revises: 20260223_0015
Create Date: 2026-02-23 15:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260223_0016"
down_revision: Union[str, Sequence[str], None] = "20260223_0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.add_column(sa.Column("agent_id", sa.String(length=64), nullable=True))
        batch_op.create_foreign_key(
            "fk_sessions_agent_id_agents",
            "agents",
            ["agent_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_index("ix_sessions_agent_id", ["agent_id"])
        batch_op.alter_column("room_id", existing_type=sa.String(length=64), nullable=True)
        batch_op.create_check_constraint(
            "ck_sessions_scope",
            "(room_id IS NOT NULL AND agent_id IS NULL) OR (room_id IS NULL AND agent_id IS NOT NULL)",
        )


def downgrade() -> None:
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.drop_constraint("ck_sessions_scope", type_="check")
        batch_op.drop_index("ix_sessions_agent_id")
        batch_op.drop_constraint("fk_sessions_agent_id_agents", type_="foreignkey")
        batch_op.drop_column("agent_id")
        batch_op.alter_column("room_id", existing_type=sa.String(length=64), nullable=False)
