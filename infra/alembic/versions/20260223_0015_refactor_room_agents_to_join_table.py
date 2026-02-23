"""refactor room_agents to agent assignment join table

Revision ID: 20260223_0015
Revises: 20260223_0014
Create Date: 2026-02-23 14:10:00
"""

from collections import defaultdict
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260223_0015"
down_revision: Union[str, Sequence[str], None] = "20260223_0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _dedupe_agent_key(*, owner_user_id: str, agent_key: str, used: dict[str, set[str]]) -> str:
    normalized = (agent_key or "").strip() or "agent"
    normalized = normalized[:64]
    chosen = normalized
    suffix_index = 2
    while chosen in used[owner_user_id]:
        suffix = f"_{suffix_index}"
        chosen = f"{normalized[: 64 - len(suffix)]}{suffix}"
        suffix_index += 1
    used[owner_user_id].add(chosen)
    return chosen


def upgrade() -> None:
    bind = op.get_bind()

    op.add_column("room_agents", sa.Column("agent_id", sa.String(length=64), nullable=True))

    rows = bind.execute(
        sa.text(
            """
            SELECT
                ra.id AS room_agent_id,
                ra.room_id AS room_id,
                ra.agent_key AS agent_key,
                ra.name AS name,
                ra.model_alias AS model_alias,
                ra.role_prompt AS role_prompt,
                ra.tool_permissions_json AS tool_permissions_json,
                ra.created_at AS created_at,
                r.owner_user_id AS owner_user_id
            FROM room_agents AS ra
            JOIN rooms AS r ON r.id = ra.room_id
            ORDER BY ra.created_at ASC, ra.id ASC
            """
        )
    ).mappings()

    used_keys: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        owner_user_id = str(row["owner_user_id"])
        room_agent_id = str(row["room_agent_id"])
        agent_key = _dedupe_agent_key(
            owner_user_id=owner_user_id,
            agent_key=str(row["agent_key"] or ""),
            used=used_keys,
        )
        bind.execute(
            sa.text(
                """
                INSERT INTO agents (
                    id, owner_user_id, agent_key, name, model_alias, role_prompt,
                    tool_permissions_json, deleted_at, created_at, updated_at
                ) VALUES (
                    :id, :owner_user_id, :agent_key, :name, :model_alias, :role_prompt,
                    :tool_permissions_json, NULL, :created_at, :updated_at
                )
                """
            ),
            {
                "id": room_agent_id,
                "owner_user_id": owner_user_id,
                "agent_key": agent_key,
                "name": str(row["name"]),
                "model_alias": str(row["model_alias"]),
                "role_prompt": str(row["role_prompt"]),
                "tool_permissions_json": str(row["tool_permissions_json"] or "[]"),
                "created_at": row["created_at"],
                "updated_at": row["created_at"],
            },
        )
        bind.execute(
            sa.text("UPDATE room_agents SET agent_id = :agent_id WHERE id = :room_agent_id"),
            {"agent_id": room_agent_id, "room_agent_id": room_agent_id},
        )

    with op.batch_alter_table("room_agents") as batch_op:
        batch_op.alter_column("agent_id", existing_type=sa.String(length=64), nullable=False)
        batch_op.create_foreign_key(
            "fk_room_agents_agent_id_agents",
            "agents",
            ["agent_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_index("ix_room_agents_agent_id", ["agent_id"])
        batch_op.drop_constraint("uq_room_agents_room_agent_key", type_="unique")
        batch_op.create_unique_constraint("uq_room_agents_room_agent_id", ["room_id", "agent_id"])
        batch_op.drop_column("agent_key")
        batch_op.drop_column("name")
        batch_op.drop_column("model_alias")
        batch_op.drop_column("role_prompt")
        batch_op.drop_column("tool_permissions_json")


def downgrade() -> None:
    bind = op.get_bind()

    with op.batch_alter_table("room_agents") as batch_op:
        batch_op.add_column(sa.Column("agent_key", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("name", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("model_alias", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("role_prompt", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("tool_permissions_json", sa.Text(), nullable=True, server_default=sa.text("'[]'"))
        )

    rows = bind.execute(
        sa.text(
            """
            SELECT
                ra.id AS room_agent_id,
                a.agent_key AS agent_key,
                a.name AS name,
                a.model_alias AS model_alias,
                a.role_prompt AS role_prompt,
                a.tool_permissions_json AS tool_permissions_json
            FROM room_agents AS ra
            JOIN agents AS a ON a.id = ra.agent_id
            """
        )
    ).mappings()
    for row in rows:
        bind.execute(
            sa.text(
                """
                UPDATE room_agents
                SET
                    agent_key = :agent_key,
                    name = :name,
                    model_alias = :model_alias,
                    role_prompt = :role_prompt,
                    tool_permissions_json = :tool_permissions_json
                WHERE id = :room_agent_id
                """
            ),
            {
                "room_agent_id": str(row["room_agent_id"]),
                "agent_key": str(row["agent_key"]),
                "name": str(row["name"]),
                "model_alias": str(row["model_alias"]),
                "role_prompt": str(row["role_prompt"]),
                "tool_permissions_json": str(row["tool_permissions_json"] or "[]"),
            },
        )

    with op.batch_alter_table("room_agents") as batch_op:
        batch_op.alter_column("agent_key", existing_type=sa.String(length=64), nullable=False)
        batch_op.alter_column("name", existing_type=sa.String(length=120), nullable=False)
        batch_op.alter_column("model_alias", existing_type=sa.String(length=64), nullable=False)
        batch_op.alter_column("role_prompt", existing_type=sa.Text(), nullable=False)
        batch_op.alter_column("tool_permissions_json", existing_type=sa.Text(), nullable=False)
        batch_op.drop_index("ix_room_agents_agent_id")
        batch_op.drop_constraint("uq_room_agents_room_agent_id", type_="unique")
        batch_op.create_unique_constraint("uq_room_agents_room_agent_key", ["room_id", "agent_key"])
        batch_op.drop_constraint("fk_room_agents_agent_id_agents", type_="foreignkey")
        batch_op.drop_column("agent_id")
