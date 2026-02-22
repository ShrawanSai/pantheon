"""create credit wallet tables

Revision ID: 20260222_0011
Revises: 20260222_0010
Create Date: 2026-02-22 23:59:50
"""

from decimal import Decimal
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260222_0011"
down_revision: Union[str, Sequence[str], None] = "20260222_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Staging placeholder beta user for initial grant seeding.
BETA_TEST_USER_ID = "11111111-1111-1111-1111-111111111111"
BETA_WALLET_ID = "beta-wallet-11111111-1111-1111-1111-111111111111"
BETA_GRANT_TX_ID = "beta-grant-11111111-1111-1111-1111-111111111111"


def upgrade() -> None:
    op.create_table(
        "credit_wallets",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("balance", sa.Numeric(precision=18, scale=8), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )

    op.create_table(
        "credit_transactions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("wallet_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("reference_id", sa.String(length=64), nullable=True),
        sa.Column("note", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("kind IN ('grant', 'debit', 'refund')", name="ck_credit_transactions_kind"),
        sa.ForeignKeyConstraint(["wallet_id"], ["credit_wallets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    credit_wallets_table = sa.table(
        "credit_wallets",
        sa.column("id", sa.String(length=64)),
        sa.column("user_id", sa.String(length=64)),
        sa.column("balance", sa.Numeric(precision=18, scale=8)),
    )
    credit_transactions_table = sa.table(
        "credit_transactions",
        sa.column("id", sa.String(length=64)),
        sa.column("wallet_id", sa.String(length=64)),
        sa.column("user_id", sa.String(length=64)),
        sa.column("amount", sa.Numeric(precision=18, scale=8)),
        sa.column("kind", sa.String(length=32)),
        sa.column("reference_id", sa.String(length=64)),
        sa.column("note", sa.String(length=256)),
    )

    op.bulk_insert(
        credit_wallets_table,
        [
            {
                "id": BETA_WALLET_ID,
                "user_id": BETA_TEST_USER_ID,
                "balance": Decimal("100.0"),
            }
        ],
    )
    op.bulk_insert(
        credit_transactions_table,
        [
            {
                "id": BETA_GRANT_TX_ID,
                "wallet_id": BETA_WALLET_ID,
                "user_id": BETA_TEST_USER_ID,
                "amount": Decimal("100.0"),
                "kind": "grant",
                "reference_id": None,
                "note": "Week 9 beta grant seed",
            }
        ],
    )


def downgrade() -> None:
    op.drop_table("credit_transactions")
    op.drop_table("credit_wallets")
