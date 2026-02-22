from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.db.models import CreditTransaction, CreditWallet


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

    async def stage_debit(
        self,
        db: AsyncSession,
        user_id: str,
        credits_burned: float,
        reference_id: str | None = None,
        note: str | None = None,
    ) -> DebitResult:
        wallet = await self.get_or_create_wallet(db, user_id=user_id)
        debit_amount = Decimal(str(max(credits_burned, 0.0)))
        current_balance = wallet.balance if wallet.balance is not None else Decimal("0")
        new_balance = current_balance - debit_amount
        wallet.balance = new_balance
        # Keep updated_at deterministic even if debit path is refactored to core UPDATE statements later.
        wallet.updated_at = datetime.now(timezone.utc)

        transaction_id = str(uuid4())
        db.add(
            CreditTransaction(
                id=transaction_id,
                wallet_id=wallet.id,
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


_wallet_service = WalletService()


def get_wallet_service() -> WalletService:
    return _wallet_service
