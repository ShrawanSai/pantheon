"""add message visibility and agent_key columns

Revision ID: 20260223_0017
Revises: 20260223_0016
Create Date: 2026-02-23 18:10:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260223_0017"
down_revision: Union[str, Sequence[str], None] = "20260223_0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("messages") as batch_op:
        batch_op.add_column(
            sa.Column(
                "visibility",
                sa.String(length=16),
                nullable=False,
                server_default=sa.text("'shared'"),
            )
        )
        batch_op.add_column(sa.Column("agent_key", sa.String(length=64), nullable=True))
        batch_op.create_check_constraint(
            "ck_messages_visibility",
            "visibility IN ('shared', 'private')",
        )


def downgrade() -> None:
    with op.batch_alter_table("messages") as batch_op:
        batch_op.drop_constraint("ck_messages_visibility", type_="check")
        batch_op.drop_column("agent_key")
        batch_op.drop_column("visibility")
