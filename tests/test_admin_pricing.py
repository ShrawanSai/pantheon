from __future__ import annotations

import asyncio
import os
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
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
from apps.api.app.db.models import Base, LlmCallEvent, ModelPricing, PricingVersion, User
from apps.api.app.db.session import get_db
from apps.api.app.dependencies.auth import get_current_user
from apps.api.app.main import app
from apps.api.app.services.usage.meter import get_model_multiplier, reload_pricing_cache


class AdminPricingRoutesTests(unittest.TestCase):
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

        cls.admin_user_id = "admin-user-1"
        cls.admin_email = "admin-user-1@example.com"
        cls.non_admin_user_id = "regular-user-1"
        cls.non_admin_email = "regular-user-1@example.com"

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
        os.environ["ADMIN_USER_IDS"] = cls.admin_user_id
        get_settings.cache_clear()

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_current_user
        cls.client = TestClient(app)

        async def seed_data() -> None:
            async with cls.session_factory() as session:
                for user_id, email in [
                    (cls.admin_user_id, cls.admin_email),
                    (cls.non_admin_user_id, cls.non_admin_email),
                ]:
                    existing = await session.get(User, user_id)
                    if existing is None:
                        session.add(User(id=user_id, email=email))

                session.add(
                    PricingVersion(
                        version="2026-02-20",
                        label="Initial pricing",
                        effective_date=date(2026, 2, 20),
                        is_active=True,
                    )
                )
                session.add(
                    ModelPricing(
                        id=str(uuid4()),
                        pricing_version="2026-02-20",
                        model_alias="deepseek",
                        multiplier=Decimal("0.5"),
                    )
                )
                session.add(
                    ModelPricing(
                        id=str(uuid4()),
                        pricing_version="2026-02-20",
                        model_alias="gpt-4o",
                        multiplier=Decimal("2.0"),
                    )
                )
                await session.commit()

        asyncio.run(seed_data())

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.clear()
        if cls._prev_admin_ids is None:
            os.environ.pop("ADMIN_USER_IDS", None)
        else:
            os.environ["ADMIN_USER_IDS"] = cls._prev_admin_ids
        get_settings.cache_clear()

        async def shutdown_db() -> None:
            async with cls.engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            await cls.engine.dispose()

        asyncio.run(shutdown_db())

    def setUp(self) -> None:
        self.__class__.current_user_id = self.__class__.admin_user_id
        self.__class__.current_user_email = self.__class__.admin_email
        reload_pricing_cache(
            {
                "deepseek": 0.5,
                "gemini-flash": 0.8,
                "gemini-pro": 1.2,
                "gpt-4o-mini": 1.0,
                "gpt-4o": 2.0,
                "claude-haiku": 0.8,
                "claude-sonnet": 1.5,
            }
        )

        async def reset_usage_events() -> None:
            async with self.session_factory() as session:
                await session.execute(delete(LlmCallEvent))
                await session.commit()

        asyncio.run(reset_usage_events())

    def test_update_multiplier_success(self) -> None:
        response = self.client.patch(
            "/api/v1/admin/pricing/gpt-4o",
            json={"multiplier": 1.5, "pricing_version": "2026-02-20"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["model_alias"], "gpt-4o")
        self.assertEqual(body["pricing_version"], "2026-02-20")
        self.assertEqual(body["multiplier"], "1.5")
        self.assertEqual(get_model_multiplier("gpt-4o"), 1.5)

        async def fetch_multiplier() -> Decimal | None:
            async with self.session_factory() as session:
                row = await session.scalar(
                    select(ModelPricing.multiplier).where(
                        ModelPricing.pricing_version == "2026-02-20",
                        ModelPricing.model_alias == "gpt-4o",
                    )
                )
                return row

        stored = asyncio.run(fetch_multiplier())
        self.assertEqual(stored, Decimal("1.5"))

    def test_update_multiplier_unknown_alias(self) -> None:
        response = self.client.patch(
            "/api/v1/admin/pricing/ghost-model",
            json={"multiplier": 1.2, "pricing_version": "2026-02-20"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Model alias not found for pricing version."})

    def test_update_multiplier_non_admin_forbidden(self) -> None:
        self.__class__.current_user_id = self.__class__.non_admin_user_id
        self.__class__.current_user_email = self.__class__.non_admin_email
        response = self.client.patch(
            "/api/v1/admin/pricing/deepseek",
            json={"multiplier": 0.6, "pricing_version": "2026-02-20"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"detail": "Admin access required."})

    def test_reload_pricing_cache_updates_get_model_multiplier(self) -> None:
        reload_pricing_cache({"deepseek": 0.9})
        self.assertEqual(get_model_multiplier("deepseek"), 0.9)
        self.assertEqual(get_model_multiplier("unknown"), 1.0)

    def _seed_usage_event(
        self,
        *,
        user_id: str,
        model_alias: str,
        credits_burned: Decimal,
        output_tokens: int,
        created_at: datetime,
    ) -> str:
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
                        output_tokens=output_tokens,
                        total_tokens=10 + output_tokens,
                        oe_tokens_computed=Decimal("8.5"),
                        provider_cost_usd=Decimal("0"),
                        credits_burned=credits_burned,
                        latency_ms=10,
                        status="success",
                        pricing_version="2026-02-20",
                        request_id=None,
                        created_at=created_at,
                    )
                )
                await session.commit()

        asyncio.run(insert_row())
        return event_id

    def test_usage_summary_empty(self) -> None:
        response = self.client.get("/api/v1/admin/usage/summary")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total_credits_burned"], "0")
        self.assertEqual(body["total_llm_calls"], 0)
        self.assertEqual(body["total_output_tokens"], 0)
        self.assertEqual(body["breakdown"], [])

    def test_usage_summary_filtered_by_user(self) -> None:
        ts = datetime(2026, 2, 22, 12, 0, 0, tzinfo=timezone.utc)
        self._seed_usage_event(
            user_id=self.admin_user_id,
            model_alias="deepseek",
            credits_burned=Decimal("0.5000"),
            output_tokens=40,
            created_at=ts,
        )
        self._seed_usage_event(
            user_id=self.non_admin_user_id,
            model_alias="gpt-4o",
            credits_burned=Decimal("2.0000"),
            output_tokens=70,
            created_at=ts,
        )

        response = self.client.get(f"/api/v1/admin/usage/summary?user_id={self.admin_user_id}")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total_llm_calls"], 1)
        self.assertEqual(body["total_credits_burned"], "0.5")
        self.assertEqual(body["total_output_tokens"], 40)
        self.assertEqual(len(body["breakdown"]), 1)
        self.assertEqual(body["breakdown"][0]["model_alias"], "deepseek")

    def test_usage_summary_filtered_by_model(self) -> None:
        ts = datetime(2026, 2, 23, 12, 0, 0, tzinfo=timezone.utc)
        self._seed_usage_event(
            user_id=self.admin_user_id,
            model_alias="deepseek",
            credits_burned=Decimal("0.7500"),
            output_tokens=30,
            created_at=ts,
        )
        self._seed_usage_event(
            user_id=self.admin_user_id,
            model_alias="gpt-4o",
            credits_burned=Decimal("1.2500"),
            output_tokens=60,
            created_at=ts,
        )

        response = self.client.get("/api/v1/admin/usage/summary?model_alias=deepseek")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total_llm_calls"], 1)
        self.assertEqual(body["total_credits_burned"], "0.75")
        self.assertEqual(body["total_output_tokens"], 30)
        self.assertEqual(len(body["breakdown"]), 1)
        self.assertEqual(body["breakdown"][0]["model_alias"], "deepseek")
        self.assertEqual(body["breakdown"][0]["call_count"], 1)

    def test_usage_summary_daily_bucket(self) -> None:
        self._seed_usage_event(
            user_id=self.admin_user_id,
            model_alias="deepseek",
            credits_burned=Decimal("0.5000"),
            output_tokens=40,
            created_at=datetime(2026, 2, 20, 12, 0, 0, tzinfo=timezone.utc),
        )
        self._seed_usage_event(
            user_id=self.admin_user_id,
            model_alias="deepseek",
            credits_burned=Decimal("0.7000"),
            output_tokens=50,
            created_at=datetime(2026, 2, 21, 12, 0, 0, tzinfo=timezone.utc),
        )
        response = self.client.get(
            "/api/v1/admin/usage/summary?bucket=day&from_date=2026-02-20&to_date=2026-02-21"
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["daily"]), 2)
        self.assertEqual(body["daily"][0]["date"], "2026-02-20")
        self.assertEqual(body["daily"][0]["call_count"], 1)
        self.assertEqual(body["daily"][1]["date"], "2026-02-21")
        self.assertEqual(body["daily"][1]["call_count"], 1)

    def test_usage_summary_no_bucket_daily_empty(self) -> None:
        self._seed_usage_event(
            user_id=self.admin_user_id,
            model_alias="deepseek",
            credits_burned=Decimal("0.5000"),
            output_tokens=40,
            created_at=datetime(2026, 2, 20, 12, 0, 0, tzinfo=timezone.utc),
        )
        response = self.client.get("/api/v1/admin/usage/summary")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["daily"], [])


if __name__ == "__main__":
    unittest.main()
