from __future__ import annotations

import asyncio
import os
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, select
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


class TopUpRoutesTests(unittest.TestCase):
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
        cls.user_id = "topup-user"
        cls.user_email = "topup-user@example.com"
        cls.admin_user_id = "topup-admin"
        cls.admin_email = "topup-admin@example.com"

        async def init_db() -> None:
            async with cls.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

        asyncio.run(init_db())

        async def override_get_db():
            async with cls.session_factory() as session:
                yield session

        def override_current_user() -> dict[str, str]:
            return {"user_id": cls.current_user_id, "email": cls.current_user_email}

        cls._prev_admin_ids = os.environ.get("ADMIN_USER_IDS")
        cls._prev_stripe_key = os.environ.get("STRIPE_SECRET_KEY")
        cls._prev_webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET")

        os.environ["ADMIN_USER_IDS"] = cls.admin_user_id
        os.environ["STRIPE_SECRET_KEY"] = "sk_test_value"
        os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_test_value"
        get_settings.cache_clear()

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_current_user
        cls.client = TestClient(app)

        async def seed_users() -> None:
            async with cls.session_factory() as session:
                for user_id, email in [
                    (cls.user_id, cls.user_email),
                    (cls.admin_user_id, cls.admin_email),
                ]:
                    if await session.get(User, user_id) is None:
                        session.add(User(id=user_id, email=email))
                await session.commit()

        asyncio.run(seed_users())

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.clear()
        if cls._prev_admin_ids is None:
            os.environ.pop("ADMIN_USER_IDS", None)
        else:
            os.environ["ADMIN_USER_IDS"] = cls._prev_admin_ids
        if cls._prev_stripe_key is None:
            os.environ.pop("STRIPE_SECRET_KEY", None)
        else:
            os.environ["STRIPE_SECRET_KEY"] = cls._prev_stripe_key
        if cls._prev_webhook_secret is None:
            os.environ.pop("STRIPE_WEBHOOK_SECRET", None)
        else:
            os.environ["STRIPE_WEBHOOK_SECRET"] = cls._prev_webhook_secret
        get_settings.cache_clear()

        async def shutdown_db() -> None:
            async with cls.engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            await cls.engine.dispose()

        asyncio.run(shutdown_db())

    def setUp(self) -> None:
        self.__class__.current_user_id = self.__class__.user_id
        self.__class__.current_user_email = self.__class__.user_email
        os.environ["STRIPE_SECRET_KEY"] = "sk_test_value"
        os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_test_value"
        get_settings.cache_clear()

        async def reset_rows() -> None:
            async with self.session_factory() as session:
                await session.execute(delete(CreditTransaction))
                await session.execute(delete(CreditWallet))
                await session.commit()

        asyncio.run(reset_rows())

    def tearDown(self) -> None:
        get_settings.cache_clear()

    def _seed_wallet(self, *, user_id: str, balance: Decimal) -> str:
        wallet_id = str(uuid4())

        async def insert_wallet() -> None:
            async with self.session_factory() as session:
                session.add(
                    CreditWallet(
                        id=wallet_id,
                        user_id=user_id,
                        balance=balance,
                    )
                )
                await session.commit()

        asyncio.run(insert_wallet())
        return wallet_id

    def test_topup_returns_client_secret(self) -> None:
        with patch(
            "apps.api.app.api.v1.routes.users.create_payment_intent",
            return_value=SimpleNamespace(client_secret="pi_secret_123"),
        ) as mock_create:
            response = self.client.post("/api/v1/users/me/wallet/top-up", json={"amount_usd": 10.00})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["client_secret"], "pi_secret_123")
        self.assertEqual(body["amount_usd"], 10.0)
        self.assertEqual(body["credits_to_grant"], 333.33)
        mock_create.assert_called_once()

    def test_topup_rejects_below_minimum(self) -> None:
        response = self.client.post("/api/v1/users/me/wallet/top-up", json={"amount_usd": 0.50})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json(), {"detail": "amount_usd must be between 1.00 and 500.00"})

    def test_topup_rejects_above_maximum(self) -> None:
        response = self.client.post("/api/v1/users/me/wallet/top-up", json={"amount_usd": 501.00})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json(), {"detail": "amount_usd must be between 1.00 and 500.00"})

    def test_topup_503_when_stripe_not_configured(self) -> None:
        os.environ["STRIPE_SECRET_KEY"] = ""
        get_settings.cache_clear()
        response = self.client.post("/api/v1/users/me/wallet/top-up", json={"amount_usd": 10.00})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "payment not configured"})

    def test_webhook_grants_credits_on_success(self) -> None:
        payment_intent_id = "pi_test_success"
        event = {
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": payment_intent_id,
                    "metadata": {"user_id": self.user_id, "credits": "100.5"},
                }
            },
        }
        with patch("apps.api.app.api.v1.routes.webhooks.construct_webhook_event", return_value=event):
            response = self.client.post(
                "/webhooks/stripe",
                content="{}",
                headers={"Stripe-Signature": "sig"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

        async def fetch_wallet_balance() -> Decimal | None:
            async with self.session_factory() as session:
                wallet = await session.scalar(select(CreditWallet).where(CreditWallet.user_id == self.user_id))
                return wallet.balance if wallet is not None else None

        balance = asyncio.run(fetch_wallet_balance())
        self.assertEqual(balance, Decimal("100.5"))

    def test_webhook_idempotent(self) -> None:
        payment_intent_id = "pi_test_idempotent"
        wallet_id = self._seed_wallet(user_id=self.user_id, balance=Decimal("50"))

        async def seed_existing_transaction() -> None:
            async with self.session_factory() as session:
                session.add(
                    CreditTransaction(
                        id=str(uuid4()),
                        wallet_id=wallet_id,
                        user_id=self.user_id,
                        amount=Decimal("10"),
                        kind="grant",
                        initiated_by=None,
                        reference_id=payment_intent_id,
                        note="stripe_topup",
                        created_at=datetime.now(timezone.utc),
                    )
                )
                await session.commit()

        asyncio.run(seed_existing_transaction())

        event = {
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": payment_intent_id,
                    "metadata": {"user_id": self.user_id, "credits": "10"},
                }
            },
        }
        with patch("apps.api.app.api.v1.routes.webhooks.construct_webhook_event", return_value=event):
            response = self.client.post("/webhooks/stripe", content="{}", headers={"Stripe-Signature": "sig"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "already_processed"})

        async def fetch_balance() -> Decimal:
            async with self.session_factory() as session:
                wallet = await session.scalar(select(CreditWallet).where(CreditWallet.id == wallet_id))
                return wallet.balance

        self.assertEqual(asyncio.run(fetch_balance()), Decimal("50"))

    def test_webhook_rejects_bad_signature(self) -> None:
        with patch(
            "apps.api.app.api.v1.routes.webhooks.construct_webhook_event",
            side_effect=ValueError("bad signature"),
        ):
            response = self.client.post("/webhooks/stripe", content="{}", headers={"Stripe-Signature": "bad"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "invalid stripe signature"})

    def test_admin_grant_increases_balance(self) -> None:
        self.__class__.current_user_id = self.__class__.admin_user_id
        self.__class__.current_user_email = self.__class__.admin_email
        self._seed_wallet(user_id=self.user_id, balance=Decimal("5"))

        response = self.client.post(
            f"/api/v1/admin/users/{self.user_id}/wallet/grant",
            json={"amount": 50.0, "note": "beta access grant"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["user_id"], self.user_id)
        self.assertEqual(body["credits_granted"], 50.0)
        self.assertEqual(body["new_balance"], "55")


if __name__ == "__main__":
    unittest.main()
