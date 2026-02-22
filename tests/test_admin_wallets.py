from __future__ import annotations

import asyncio
import os
import unittest
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Keep import-time settings self-contained for CI/local test runs.
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "dummy-service-role-key")
os.environ.setdefault("API_CORS_ALLOWED_ORIGINS", "http://localhost:3000")

from apps.api.app.core.config import get_settings
from apps.api.app.db.models import Base, CreditTransaction, CreditWallet, User
from apps.api.app.db.session import get_db
from apps.api.app.dependencies.auth import get_current_user
from apps.api.app.main import app


class AdminWalletRoutesTests(unittest.TestCase):
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
        cls.admin_user_id = "admin-wallet-user"
        cls.admin_email = "admin-wallet-user@example.com"
        cls.non_admin_user_id = "regular-wallet-user"
        cls.non_admin_email = "regular-wallet-user@example.com"
        cls.target_user_id = "wallet-target-user"
        cls.target_email = "wallet-target-user@example.com"

        async def init_db() -> None:
            async with cls.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

        asyncio.run(init_db())

        async def override_get_db():
            async with cls.session_factory() as session:
                yield session

        def override_current_user() -> dict[str, str]:
            return {"user_id": cls.current_user_id, "email": cls.current_user_email}

        cls._prev_admin_user_ids = os.environ.get("ADMIN_USER_IDS")
        os.environ["ADMIN_USER_IDS"] = cls.admin_user_id
        get_settings.cache_clear()

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_current_user
        cls.client = TestClient(app)

        async def seed_users() -> None:
            async with cls.session_factory() as session:
                for user_id, email in [
                    (cls.admin_user_id, cls.admin_email),
                    (cls.non_admin_user_id, cls.non_admin_email),
                    (cls.target_user_id, cls.target_email),
                ]:
                    existing = await session.get(User, user_id)
                    if existing is None:
                        session.add(User(id=user_id, email=email))
                await session.commit()

        asyncio.run(seed_users())

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.clear()
        if cls._prev_admin_user_ids is None:
            os.environ.pop("ADMIN_USER_IDS", None)
        else:
            os.environ["ADMIN_USER_IDS"] = cls._prev_admin_user_ids
        get_settings.cache_clear()

        async def shutdown_db() -> None:
            async with cls.engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            await cls.engine.dispose()

        asyncio.run(shutdown_db())

    def setUp(self) -> None:
        self.__class__.current_user_id = self.__class__.admin_user_id
        self.__class__.current_user_email = self.__class__.admin_email

        async def reset_wallet_data() -> None:
            async with self.session_factory() as session:
                await session.execute(CreditTransaction.__table__.delete())
                await session.execute(CreditWallet.__table__.delete())
                await session.commit()

        asyncio.run(reset_wallet_data())

    def _seed_wallet_with_transactions(self) -> str:
        wallet_id = str(uuid4())

        async def insert_rows() -> None:
            async with self.session_factory() as session:
                session.add(
                    CreditWallet(
                        id=wallet_id,
                        user_id=self.target_user_id,
                        balance=Decimal("12.5"),
                    )
                )
                session.add(
                    CreditTransaction(
                        id=str(uuid4()),
                        wallet_id=wallet_id,
                        user_id=self.target_user_id,
                        amount=Decimal("10"),
                        kind="grant",
                        reference_id=None,
                        note="seed grant",
                    )
                )
                session.add(
                    CreditTransaction(
                        id=str(uuid4()),
                        wallet_id=wallet_id,
                        user_id=self.target_user_id,
                        amount=Decimal("-2.5"),
                        kind="debit",
                        reference_id="turn-1",
                        note="seed debit",
                    )
                )
                await session.commit()

        asyncio.run(insert_rows())
        return wallet_id

    def test_get_wallet_returns_balance_and_transactions(self) -> None:
        self._seed_wallet_with_transactions()
        response = self.client.get(f"/api/v1/admin/wallets/{self.target_user_id}")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["user_id"], self.target_user_id)
        self.assertEqual(body["balance"], "12.5")
        self.assertEqual(len(body["recent_transactions"]), 2)
        self.assertIn(body["recent_transactions"][0]["kind"], {"grant", "debit"})

    def test_get_wallet_not_found(self) -> None:
        response = self.client.get("/api/v1/admin/wallets/nonexistent-user")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Wallet not found."})

    def test_grant_increases_balance(self) -> None:
        self._seed_wallet_with_transactions()
        before_response = self.client.get(f"/api/v1/admin/wallets/{self.target_user_id}")
        self.assertEqual(before_response.status_code, 200)
        before_balance = Decimal(before_response.json()["balance"])

        grant_response = self.client.post(
            f"/api/v1/admin/wallets/{self.target_user_id}/grant",
            json={"amount": 3.25, "note": "manual adjustment"},
        )
        self.assertEqual(grant_response.status_code, 200)
        self.assertEqual(grant_response.json()["user_id"], self.target_user_id)
        self.assertTrue(grant_response.json()["transaction_id"])

        after_response = self.client.get(f"/api/v1/admin/wallets/{self.target_user_id}")
        self.assertEqual(after_response.status_code, 200)
        after_balance = Decimal(after_response.json()["balance"])
        self.assertEqual(after_balance, before_balance + Decimal("3.25"))

    def test_grant_non_admin_forbidden(self) -> None:
        self._seed_wallet_with_transactions()
        self.__class__.current_user_id = self.__class__.non_admin_user_id
        self.__class__.current_user_email = self.__class__.non_admin_email
        response = self.client.post(
            f"/api/v1/admin/wallets/{self.target_user_id}/grant",
            json={"amount": 1.0},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"detail": "Admin access required."})


if __name__ == "__main__":
    unittest.main()
