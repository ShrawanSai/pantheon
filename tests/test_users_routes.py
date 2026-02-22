from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import os
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Keep import-time settings self-contained for CI/local test runs.
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "dummy-service-role-key")
os.environ.setdefault("API_CORS_ALLOWED_ORIGINS", "http://localhost:3000")

from apps.api.app.db.models import Base, CreditWallet, LlmCallEvent, User
from apps.api.app.db.session import get_db
from apps.api.app.dependencies.auth import get_current_user
from apps.api.app.main import app


class UsersRoutesTests(unittest.TestCase):
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
        cls.auth_user_id = "users-test-default"
        cls.auth_email = "users-test-default@example.com"

        async def init_db() -> None:
            async with cls.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

        asyncio.run(init_db())

        async def override_get_db():
            async with cls.session_factory() as session:
                yield session

        def override_current_user() -> dict[str, str]:
            return {"user_id": cls.auth_user_id, "email": cls.auth_email}

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_current_user
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.clear()

        async def shutdown_db() -> None:
            async with cls.engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            await cls.engine.dispose()

        asyncio.run(shutdown_db())

    def _set_auth_user(self, *, user_id: str, email: str) -> None:
        self.__class__.auth_user_id = user_id
        self.__class__.auth_email = email

    def _seed_user(self, *, user_id: str, email: str) -> None:
        async def insert_row() -> None:
            async with self.session_factory() as session:
                existing = await session.get(User, user_id)
                if existing is None:
                    session.add(User(id=user_id, email=email))
                    await session.commit()

        asyncio.run(insert_row())

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

    def _seed_usage_event(self, *, user_id: str, model_alias: str, credits_burned: Decimal) -> str:
        event_id = str(uuid4())

        async def insert_row() -> None:
            async with self.session_factory() as session:
                session.add(
                    LlmCallEvent(
                        id=event_id,
                        user_id=user_id,
                        room_id=None,
                        direct_session_id=None,
                        session_id=None,
                        turn_id=None,
                        step_id=None,
                        agent_id=None,
                        provider="openrouter",
                        model_alias=model_alias,
                        provider_model=f"{model_alias}/provider",
                        input_tokens_fresh=10,
                        input_tokens_cached=0,
                        output_tokens=5,
                        total_tokens=15,
                        oe_tokens_computed=Decimal("8.5"),
                        provider_cost_usd=Decimal("0"),
                        credits_burned=credits_burned,
                        latency_ms=10,
                        status="success",
                        pricing_version="2026-02-20",
                        request_id=None,
                        created_at=datetime.now(timezone.utc),
                    )
                )
                await session.commit()

        asyncio.run(insert_row())
        return event_id

    def test_get_wallet_no_existing_wallet(self) -> None:
        user_id = f"user-{uuid4()}"
        email = f"{user_id}@example.com"
        self._set_auth_user(user_id=user_id, email=email)
        self._seed_user(user_id=user_id, email=email)

        response = self.client.get("/api/v1/users/me/wallet")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "user_id": user_id,
                "balance": "0",
            },
        )

    def test_get_wallet_existing_balance(self) -> None:
        user_id = f"user-{uuid4()}"
        email = f"{user_id}@example.com"
        self._set_auth_user(user_id=user_id, email=email)
        self._seed_user(user_id=user_id, email=email)
        self._seed_wallet(user_id=user_id, balance=Decimal("5.25"))

        response = self.client.get("/api/v1/users/me/wallet")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user_id"], user_id)
        self.assertEqual(response.json()["balance"], "5.25")

    def test_get_usage_empty(self) -> None:
        user_id = f"user-{uuid4()}"
        email = f"{user_id}@example.com"
        self._set_auth_user(user_id=user_id, email=email)
        self._seed_user(user_id=user_id, email=email)

        response = self.client.get("/api/v1/users/me/usage")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"events": [], "total": 0})

    def test_get_usage_filters_by_user(self) -> None:
        requesting_user_id = f"user-{uuid4()}"
        requesting_email = f"{requesting_user_id}@example.com"
        other_user_id = f"user-{uuid4()}"
        other_email = f"{other_user_id}@example.com"
        self._set_auth_user(user_id=requesting_user_id, email=requesting_email)
        self._seed_user(user_id=requesting_user_id, email=requesting_email)
        self._seed_user(user_id=other_user_id, email=other_email)

        own_event_id = self._seed_usage_event(
            user_id=requesting_user_id,
            model_alias="deepseek",
            credits_burned=Decimal("0.5"),
        )
        self._seed_usage_event(
            user_id=other_user_id,
            model_alias="gpt-4o",
            credits_burned=Decimal("2.0"),
        )

        response = self.client.get("/api/v1/users/me/usage?limit=50&offset=0")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(len(body["events"]), 1)
        self.assertEqual(body["events"][0]["id"], own_event_id)
        self.assertEqual(body["events"][0]["model_alias"], "deepseek")
        self.assertEqual(body["events"][0]["credits_burned"], "0.5")


if __name__ == "__main__":
    unittest.main()
