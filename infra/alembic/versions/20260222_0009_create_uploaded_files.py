"""create uploaded_files table

Revision ID: 20260222_0009
Revises: 20260222_0008
Create Date: 2026-02-22 23:59:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260222_0009"
down_revision: Union[str, Sequence[str], None] = "20260222_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "uploaded_files",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("room_id", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("parse_status", sa.String(length=16), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("parsed_text", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint(
            "parse_status IN ('pending', 'completed', 'failed')",
            name="ck_uploaded_files_parse_status",
        ),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_uploaded_files_room_id", "uploaded_files", ["room_id"])


def downgrade() -> None:
    op.drop_index("ix_uploaded_files_room_id", table_name="uploaded_files")
    op.drop_table("uploaded_files")

