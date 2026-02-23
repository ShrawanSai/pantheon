from __future__ import annotations

import asyncio
import os
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "dummy-service-role-key")
os.environ.setdefault("API_CORS_ALLOWED_ORIGINS", "http://localhost:3000")

from apps.api.app.core.config import get_settings
from apps.api.app.db.models import Agent, Base, LlmCallEvent, Session, User
from apps.api.app.db.session import get_db
from apps.api.app.dependencies.auth import get_current_user
from apps.api.app.main import app


class AdminAnalyticsRoutesTests(unittest.TestCase):
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

        cls.admin_user_id = "analytics-admin"
        cls.admin_email = "analytics-admin@example.com"
        cls.non_admin_user_id = "analytics-user"
        cls.non_admin_email = "analytics-user@example.com"
        cls.current_user_id = cls.admin_user_id
        cls.current_user_email = cls.admin_email

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

        async def reset_rows() -> None:
            async with self.session_factory() as session:
                await session.execute(delete(LlmCallEvent))
                await session.execute(delete(Session))
                await session.execute(delete(Agent))
                await session.execute(delete(User))
                await session.commit()

        asyncio.run(reset_rows())

    def _ensure_user(self, user_id: str, email: str | None = None) -> None:
        email_value = email or f"{user_id}@example.com"

        async def insert_user() -> None:
            async with self.session_factory() as session:
                existing = await session.get(User, user_id)
                if existing is None:
                    session.add(User(id=user_id, email=email_value))
                    await session.commit()

        asyncio.run(insert_user())

    def _seed_session(self, *, user_id: str, created_at: datetime) -> str:
        session_id = str(uuid4())
        agent_id = str(uuid4())
        self._ensure_user(user_id)

        async def insert_rows() -> None:
            async with self.session_factory() as session:
                session.add(
                    Agent(
                        id=agent_id,
                        owner_user_id=user_id,
                        agent_key=f"agent-{agent_id[:8]}",
                        name="Analytics Agent",
                        model_alias="deepseek",
                        role_prompt="analytics",
                        tool_permissions_json="[]",
                    )
                )
                session.add(
                    Session(
                        id=session_id,
                        room_id=None,
                        agent_id=agent_id,
                        started_by_user_id=user_id,
                        created_at=created_at,
                    )
                )
                await session.commit()

        asyncio.run(insert_rows())
        return session_id

    def _seed_usage_event(
        self,
        *,
        user_id: str,
        model_alias: str,
        created_at: datetime,
        credits_burned: Decimal,
        input_tokens_fresh: int,
        input_tokens_cached: int,
        output_tokens: int,
    ) -> str:
        event_id = str(uuid4())
        self._ensure_user(user_id)

        async def insert_event() -> None:
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
                        input_tokens_fresh=input_tokens_fresh,
                        input_tokens_cached=input_tokens_cached,
                        output_tokens=output_tokens,
                        total_tokens=input_tokens_fresh + input_tokens_cached + output_tokens,
                        oe_tokens_computed=Decimal("1.0"),
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

        asyncio.run(insert_event())
        return event_id

    def test_usage_analytics_aggregates_by_user_model(self) -> None:
        ts1 = datetime(2026, 2, 21, 10, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2026, 2, 22, 10, 0, 0, tzinfo=timezone.utc)

        self._seed_usage_event(
            user_id="user-a",
            model_alias="deepseek",
            created_at=ts1,
            credits_burned=Decimal("0.5"),
            input_tokens_fresh=100,
            input_tokens_cached=20,
            output_tokens=40,
        )
        self._seed_usage_event(
            user_id="user-a",
            model_alias="deepseek",
            created_at=ts2,
            credits_burned=Decimal("0.7"),
            input_tokens_fresh=50,
            input_tokens_cached=10,
            output_tokens=60,
        )
        self._seed_usage_event(
            user_id="user-b",
            model_alias="qwen",
            created_at=ts2,
            credits_burned=Decimal("0.3"),
            input_tokens_fresh=80,
            input_tokens_cached=0,
            output_tokens=30,
        )

        response = self.client.get(
            "/api/v1/admin/analytics/usage?start_date=2026-02-21&end_date=2026-02-23"
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 2)
        self.assertEqual(body["start_date"], "2026-02-21")
        self.assertEqual(body["end_date"], "2026-02-23")

        by_key = {(row["user_id"], row["model_alias"]): row for row in body["rows"]}
        deepseek_row = by_key[("user-a", "deepseek")]
        self.assertEqual(deepseek_row["total_input_tokens"], 180)
        self.assertEqual(deepseek_row["total_output_tokens"], 100)
        self.assertEqual(deepseek_row["total_credits_burned"], "1.2")
        self.assertEqual(deepseek_row["event_count"], 2)

        qwen_row = by_key[("user-b", "qwen")]
        self.assertEqual(qwen_row["total_input_tokens"], 80)
        self.assertEqual(qwen_row["total_output_tokens"], 30)
        self.assertEqual(qwen_row["total_credits_burned"], "0.3")
        self.assertEqual(qwen_row["event_count"], 1)

    def test_usage_analytics_filters_by_date_range(self) -> None:
        self._seed_usage_event(
            user_id="user-a",
            model_alias="deepseek",
            created_at=datetime(2026, 2, 20, 23, 59, 0, tzinfo=timezone.utc),
            credits_burned=Decimal("0.4"),
            input_tokens_fresh=30,
            input_tokens_cached=0,
            output_tokens=10,
        )
        self._seed_usage_event(
            user_id="user-a",
            model_alias="deepseek",
            created_at=datetime(2026, 2, 21, 12, 0, 0, tzinfo=timezone.utc),
            credits_burned=Decimal("0.6"),
            input_tokens_fresh=70,
            input_tokens_cached=5,
            output_tokens=20,
        )

        response = self.client.get(
            "/api/v1/admin/analytics/usage?start_date=2026-02-21&end_date=2026-02-21"
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(len(body["rows"]), 1)
        row = body["rows"][0]
        self.assertEqual(row["event_count"], 1)
        self.assertEqual(row["total_input_tokens"], 75)
        self.assertEqual(row["total_output_tokens"], 20)
        self.assertEqual(row["total_credits_burned"], "0.6")

    def test_usage_analytics_non_admin_rejected(self) -> None:
        self.__class__.current_user_id = self.__class__.non_admin_user_id
        self.__class__.current_user_email = self.__class__.non_admin_email
        response = self.client.get(
            "/api/v1/admin/analytics/usage?start_date=2026-02-21&end_date=2026-02-21"
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"detail": "Admin access required."})

    def test_active_users_day_window(self) -> None:
        self._seed_session(
            user_id="u1",
            created_at=datetime(2026, 2, 23, 1, 0, 0, tzinfo=timezone.utc),
        )
        self._seed_session(
            user_id="u2",
            created_at=datetime(2026, 2, 23, 5, 0, 0, tzinfo=timezone.utc),
        )
        self._seed_session(
            user_id="u3",
            created_at=datetime(2026, 2, 22, 20, 0, 0, tzinfo=timezone.utc),
        )

        response = self.client.get("/api/v1/admin/analytics/active-users?window=day&as_of=2026-02-23")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["window"], "day")
        self.assertEqual(body["as_of"], "2026-02-23")
        self.assertEqual(body["active_users"], 2)

    def test_active_users_week_window(self) -> None:
        self._seed_session(
            user_id="u1",
            created_at=datetime(2026, 2, 23, 1, 0, 0, tzinfo=timezone.utc),
        )
        self._seed_session(
            user_id="u2",
            created_at=datetime(2026, 2, 20, 5, 0, 0, tzinfo=timezone.utc),
        )
        self._seed_session(
            user_id="u3",
            created_at=datetime(2026, 2, 17, 9, 0, 0, tzinfo=timezone.utc),
        )
        self._seed_session(
            user_id="u4",
            created_at=datetime(2026, 2, 16, 23, 0, 0, tzinfo=timezone.utc),
        )

        response = self.client.get("/api/v1/admin/analytics/active-users?window=week&as_of=2026-02-23")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["window"], "week")
        self.assertEqual(body["active_users"], 3)

    def test_active_users_new_users_count(self) -> None:
        today = datetime(2026, 2, 23, 12, 0, 0, tzinfo=timezone.utc)

        self._seed_session(user_id="n1", created_at=today)
        self._seed_session(user_id="n2", created_at=today)
        self._seed_session(user_id="n3", created_at=today)

        self._seed_session(
            user_id="existing",
            created_at=datetime(2026, 2, 20, 8, 0, 0, tzinfo=timezone.utc),
        )
        self._seed_session(user_id="existing", created_at=today)

        response = self.client.get("/api/v1/admin/analytics/active-users?window=day&as_of=2026-02-23")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["active_users"], 4)
        self.assertEqual(body["new_users"], 3)

    def test_active_users_non_admin_rejected(self) -> None:
        self.__class__.current_user_id = self.__class__.non_admin_user_id
        self.__class__.current_user_email = self.__class__.non_admin_email
        response = self.client.get("/api/v1/admin/analytics/active-users?window=day&as_of=2026-02-23")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"detail": "Admin access required."})


if __name__ == "__main__":
    unittest.main()
