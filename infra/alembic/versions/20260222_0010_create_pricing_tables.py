"""create pricing version tables

Revision ID: 20260222_0010
Revises: 20260222_0009
Create Date: 2026-02-22 23:59:30
"""

from datetime import date
from decimal import Decimal
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "20260222_0010"
down_revision: Union[str, Sequence[str], None] = "20260222_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PRICING_VERSION = "2026-02-20"
MODEL_MULTIPLIERS: dict[str, Decimal] = {
    "deepseek": Decimal("0.5"),
    "gemini-flash": Decimal("0.8"),
    "gemini-pro": Decimal("1.2"),
    "gpt-4o-mini": Decimal("1.0"),
    "gpt-4o": Decimal("2.0"),
    "claude-haiku": Decimal("0.8"),
    "claude-sonnet": Decimal("1.5"),
}


def upgrade() -> None:
    op.create_table(
        "pricing_versions",
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("version"),
    )

    op.create_table(
        "model_pricing",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("pricing_version", sa.String(length=32), nullable=False),
        sa.Column("model_alias", sa.String(length=128), nullable=False),
        sa.Column("multiplier", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["pricing_version"], ["pricing_versions.version"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pricing_version", "model_alias"),
    )

    pricing_versions_table = sa.table(
        "pricing_versions",
        sa.column("version", sa.String(length=32)),
        sa.column("label", sa.String(length=128)),
        sa.column("effective_date", sa.Date()),
        sa.column("is_active", sa.Boolean()),
    )
    model_pricing_table = sa.table(
        "model_pricing",
        sa.column("id", sa.String(length=64)),
        sa.column("pricing_version", sa.String(length=32)),
        sa.column("model_alias", sa.String(length=128)),
        sa.column("multiplier", sa.Numeric(precision=10, scale=4)),
    )

    op.bulk_insert(
        pricing_versions_table,
        [
            {
                "version": PRICING_VERSION,
                "label": "Initial pricing",
                "effective_date": date(2026, 2, 20),
                "is_active": True,
            }
        ],
    )

    op.bulk_insert(
        model_pricing_table,
        [
            {
                "id": str(uuid4()),
                "pricing_version": PRICING_VERSION,
                "model_alias": alias,
                "multiplier": multiplier,
            }
            for alias, multiplier in MODEL_MULTIPLIERS.items()
        ],
    )


def downgrade() -> None:
    op.drop_table("model_pricing")
    op.drop_table("pricing_versions")
