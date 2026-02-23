"""create agents table

Revision ID: 20260223_0014
Revises: 20260223_0013
Create Date: 2026-02-23 13:30:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260223_0014"
down_revision: Union[str, Sequence[str], None] = "20260223_0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("owner_user_id", sa.String(length=64), nullable=False),
        sa.Column("agent_key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("model_alias", sa.String(length=64), nullable=False),
        sa.Column("role_prompt", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("tool_permissions_json", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("owner_user_id", "agent_key", name="uq_agents_owner_agent_key"),
    )
    op.create_index("ix_agents_owner_user_id", "agents", ["owner_user_id"])


def downgrade() -> None:
    op.drop_index("ix_agents_owner_user_id", table_name="agents")
    op.drop_table("agents")
