from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.db.models import CreditTransaction, CreditWallet

# Precision contract:
# - credit_transactions.amount: Numeric(18,8) -> ledger truth, full precision
# - llm_call_events.credits_burned: Numeric(20,4) -> usage summary, display precision
# These are intentionally different. Do not normalize across them.


@dataclass(frozen=True)
class DebitResult:
    success: bool
    new_balance: Decimal
    transaction_id: str | None
    error: str | None


class WalletService:
    async def get_or_create_wallet(self, db: AsyncSession, user_id: str) -> CreditWallet:
        wallet = await db.scalar(select(CreditWallet).where(CreditWallet.user_id == user_id))
        if wallet is not None:
            return wallet

        wallet = CreditWallet(
            id=str(uuid4()),
            user_id=user_id,
            balance=Decimal("0"),
        )
        db.add(wallet)
        await db.flush()
        return wallet

    # initiated_by convention:
    # - Debits leave initiated_by=None for system-driven turns.
    # - user_id identifies the account and reference_id carries turn context.
    # - Any future admin-forced debit path must explicitly pass initiated_by=admin_user_id.
    # - Do not backfill historical debit rows.
    async def stage_debit(
        self,
        db: AsyncSession,
        user_id: str,
        credits_burned: float,
        reference_id: str | None = None,
        note: str | None = None,
    ) -> DebitResult:
        debit_amount = Decimal(str(max(credits_burned, 0.0)))
        now = datetime.now(timezone.utc)

        # Atomic UPDATE avoids the read-modify-write race condition that occurs
        # when two concurrent requests both read the same balance before either writes.
        # RETURNING gives us the post-update balance without a second SELECT.
        result = await db.execute(
            update(CreditWallet)
            .where(CreditWallet.user_id == user_id)
            .values(
                balance=CreditWallet.balance - debit_amount,
                updated_at=now,
            )
            .returning(CreditWallet.balance, CreditWallet.id)
        )
        row = result.one_or_none()

        if row is None:
            # Wallet does not exist yet — create it, then apply debit on the new row.
            wallet = await self.get_or_create_wallet(db, user_id=user_id)
            wallet.balance = (wallet.balance or Decimal("0")) - debit_amount
            wallet.updated_at = now
            new_balance = wallet.balance
            wallet_id = wallet.id
        else:
            new_balance, wallet_id = row

        transaction_id = str(uuid4())
        db.add(
            CreditTransaction(
                id=transaction_id,
                wallet_id=wallet_id,
                user_id=user_id,
                amount=-debit_amount,
                kind="debit",
                reference_id=reference_id,
                note=note,
            )
        )
        return DebitResult(
            success=True,
            new_balance=new_balance,
            transaction_id=transaction_id,
            error=None,
        )

    async def stage_grant(
        self,
        db: AsyncSession,
        user_id: str,
        amount: float,
        note: str | None = None,
        reference_id: str | None = None,
        initiated_by: str | None = None,
    ) -> DebitResult:
        grant_amount = Decimal(str(max(amount, 0.0)))
        wallet = await self.get_or_create_wallet(db, user_id=user_id)
        current_balance = wallet.balance if wallet.balance is not None else Decimal("0")
        new_balance = current_balance + grant_amount
        wallet.balance = new_balance
        wallet.updated_at = datetime.now(timezone.utc)

        transaction_id = str(uuid4())
        db.add(
            CreditTransaction(
                id=transaction_id,
                wallet_id=wallet.id,
                user_id=user_id,
                amount=grant_amount,
                kind="grant",
                initiated_by=initiated_by,
                reference_id=reference_id,
                note=note,
            )
        )
        return DebitResult(
            success=True,
            new_balance=new_balance,
            transaction_id=transaction_id,
            error=None,
        )


_wallet_service = WalletService()


def get_wallet_service() -> WalletService:
    return _wallet_service
