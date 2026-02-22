from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from apps.api.app.db.models import Base, CreditTransaction, CreditWallet
from apps.api.app.services.billing.wallet import WalletService


class WalletServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.session_factory = async_sessionmaker(
            bind=cls.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

        async def init_db() -> None:
            async with cls.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

        asyncio.run(init_db())

    @classmethod
    def tearDownClass(cls) -> None:
        async def shutdown_db() -> None:
            async with cls.engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            await cls.engine.dispose()

        asyncio.run(shutdown_db())

    def _seed_wallet(self, *, user_id: str, balance: Decimal) -> str:
        wallet_id = str(uuid4())

        async def insert_row() -> None:
            async with self.session_factory() as session:
                session.add(
                    CreditWallet(
                        id=wallet_id,
                        user_id=user_id,
                        balance=balance,
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                    )
                )
                await session.commit()

        asyncio.run(insert_row())
        return wallet_id

    def test_get_or_create_creates_wallet(self) -> None:
        service = WalletService()
        user_id = f"user-{uuid4()}"

        async def run() -> CreditWallet:
            async with self.session_factory() as session:
                wallet = await service.get_or_create_wallet(session, user_id=user_id)
                await session.commit()
                return wallet

        wallet = asyncio.run(run())
        self.assertEqual(wallet.user_id, user_id)
        self.assertEqual(wallet.balance, Decimal("0"))

    def test_get_or_create_idempotent(self) -> None:
        service = WalletService()
        user_id = f"user-{uuid4()}"

        # Avoid SQLAlchemy count() on select for compatibility in sqlite test path.
        async def run_count() -> int:
            async with self.session_factory() as session:
                rows = await session.scalars(select(CreditWallet).where(CreditWallet.user_id == user_id))
                return len(rows.all())

        async def run_ids() -> tuple[str, str]:
            async with self.session_factory() as session:
                wallet_first = await service.get_or_create_wallet(session, user_id=user_id)
                wallet_second = await service.get_or_create_wallet(session, user_id=user_id)
                await session.commit()
                return wallet_first.id, wallet_second.id

        first_id, second_id = asyncio.run(run_ids())
        wallet_count = asyncio.run(run_count())
        self.assertEqual(first_id, second_id)
        self.assertEqual(wallet_count, 1)

    def test_stage_debit_reduces_balance(self) -> None:
        service = WalletService()
        user_id = f"user-{uuid4()}"
        self._seed_wallet(user_id=user_id, balance=Decimal("10.0"))

        async def run() -> Decimal:
            async with self.session_factory() as session:
                result = await service.stage_debit(
                    session,
                    user_id=user_id,
                    credits_burned=0.5,
                    reference_id="turn-1",
                    note="turn:turn-1",
                )
                await session.flush()
                self.assertTrue(result.success)
                return result.new_balance

        new_balance = asyncio.run(run())
        self.assertEqual(new_balance, Decimal("9.5"))

    def test_stage_debit_creates_transaction_row(self) -> None:
        service = WalletService()
        user_id = f"user-{uuid4()}"
        self._seed_wallet(user_id=user_id, balance=Decimal("10.0"))

        async def run() -> tuple[int, str, Decimal]:
            async with self.session_factory() as session:
                await service.stage_debit(
                    session,
                    user_id=user_id,
                    credits_burned=0.5,
                    reference_id="turn-2",
                    note="turn:turn-2",
                )
                await session.flush()
                rows = await session.scalars(
                    select(CreditTransaction).where(CreditTransaction.user_id == user_id)
                )
                items = rows.all()
                tx = items[0]
                return len(items), tx.kind, tx.amount

        count, kind, amount = asyncio.run(run())
        self.assertEqual(count, 1)
        self.assertEqual(kind, "debit")
        self.assertEqual(amount, Decimal("-0.5"))

    def test_stage_debit_does_not_commit(self) -> None:
        service = WalletService()
        user_id = f"user-{uuid4()}"

        async def run() -> bool:
            async with self.session_factory() as session:
                with patch.object(session, "commit", new_callable=AsyncMock) as commit_mock:
                    await service.stage_debit(
                        session,
                        user_id=user_id,
                        credits_burned=0.5,
                        reference_id="turn-3",
                        note="turn:turn-3",
                    )
                    commit_mock.assert_not_called()
                    return session.in_transaction() is not None

        self.assertTrue(asyncio.run(run()))


if __name__ == "__main__":
    unittest.main()
