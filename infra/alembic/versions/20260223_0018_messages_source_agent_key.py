"""add source_agent_key attribution column to messages

Revision ID: 20260223_0018
Revises: 20260223_0017
Create Date: 2026-02-23 21:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260223_0018"
down_revision: Union[str, Sequence[str], None] = "20260223_0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("messages") as batch_op:
        batch_op.add_column(sa.Column("source_agent_key", sa.String(length=64), nullable=True))

    op.execute("UPDATE messages SET source_agent_key = agent_key WHERE agent_key IS NOT NULL")


def downgrade() -> None:
    with op.batch_alter_table("messages") as batch_op:
        batch_op.drop_column("source_agent_key")

