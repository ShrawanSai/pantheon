from __future__ import annotations

import asyncio
import os
import unittest
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from uuid import uuid4
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "dummy-service-role-key")
os.environ.setdefault("API_CORS_ALLOWED_ORIGINS", "http://localhost:3000")

from apps.api.app.core.config import get_settings
from apps.api.app.db.models import Agent, Base, Session, User
from apps.api.app.db.session import get_db
from apps.api.app.dependencies.auth import get_current_user
from apps.api.app.main import app
from apps.api.app.services.llm.gateway import (
    GatewayRequest,
    GatewayResponse,
    GatewayUsage,
    StreamingContext,
    get_llm_gateway,
)
from apps.api.app.services.orchestration.mode_executor import (
    TurnExecutionState,
    get_mode_executor,
)
from apps.api.app.services.usage.recorder import UsageRecord, get_usage_recorder


@dataclass
class FakeRedisPool:
    counts: dict[str, int] = field(default_factory=dict)
    expiries: dict[str, int] = field(default_factory=dict)

    async def incr(self, key: str) -> int:
        value = self.counts.get(key, 0) + 1
        self.counts[key] = value
        return value

    async def expire(self, key: str, ttl: int) -> bool:
        self.expiries[key] = ttl
        return True


@dataclass
class FakeGateway:
    stream_chunks: list[str] = field(default_factory=lambda: ["hello", " ", "stream"])

    async def generate(self, request: GatewayRequest) -> GatewayResponse:
        _ = request
        return GatewayResponse(
            text="ok",
            provider_model="fake/provider",
            usage=GatewayUsage(
                input_tokens_fresh=10,
                input_tokens_cached=0,
                output_tokens=5,
                total_tokens=15,
            ),
        )

    async def stream(self, request: GatewayRequest) -> StreamingContext:
        _ = request
        usage_future = asyncio.get_running_loop().create_future()
        provider_model_future = asyncio.get_running_loop().create_future()

        async def _iter() -> AsyncIterator[str]:
            for chunk in self.stream_chunks:
                yield chunk
            usage_future.set_result(
                GatewayUsage(
                    input_tokens_fresh=10,
                    input_tokens_cached=0,
                    output_tokens=5,
                    total_tokens=15,
                )
            )
            provider_model_future.set_result("fake/provider")

        return StreamingContext(
            chunks=_iter(),
            usage_future=usage_future,
            provider_model_future=provider_model_future,
        )


@dataclass
class FakeModeExecutor:
    async def run_turn(self, db: AsyncSession, state: TurnExecutionState, event_sink=None) -> TurnExecutionState:
        _ = db
        agent = state.active_agents[0] if state.active_agents else None
        state.assistant_entries.append((agent, "ok"))
        state.usage_entries.append((agent.agent_id if agent else None, agent.model_alias if agent else "fake", "fake/provider", 10, 0, 5, 15))
        return state


@dataclass
class FakeUsageRecorder:
    records: list[UsageRecord] = field(default_factory=list)

    async def stage_llm_usage(self, db: AsyncSession, record: UsageRecord) -> None:
        _ = db
        self.records.append(record)

    async def record_llm_usage(self, db: AsyncSession, record: UsageRecord) -> None:
        await self.stage_llm_usage(db, record)


class RateLimitingTests(unittest.TestCase):
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
        cls.current_user_id = "ratelimit-user"
        cls.current_email = "ratelimit-user@example.com"
        cls.fake_gateway = FakeGateway()
        cls.fake_usage_recorder = FakeUsageRecorder()
        cls.fake_mode_executor = FakeModeExecutor()

        async def init_db() -> None:
            async with cls.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

        asyncio.run(init_db())

        async def override_get_db():
            async with cls.session_factory() as session:
                yield session

        def override_current_user() -> dict[str, str]:
            return {"user_id": cls.current_user_id, "email": cls.current_email}

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_current_user
        app.dependency_overrides[get_llm_gateway] = lambda: cls.fake_gateway
        app.dependency_overrides[get_mode_executor] = lambda: cls.fake_mode_executor
        app.dependency_overrides[get_usage_recorder] = lambda: cls.fake_usage_recorder
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.clear()

        async def shutdown_db() -> None:
            async with cls.engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            await cls.engine.dispose()

        asyncio.run(shutdown_db())

    def setUp(self) -> None:
        get_settings.cache_clear()
        self.fake_usage_recorder.records.clear()
        app.state.arq_redis = FakeRedisPool()

        async def reset_rows() -> None:
            async with self.session_factory() as session:
                await session.execute(delete(Session))
                await session.execute(delete(Agent))
                await session.execute(delete(User))
                await session.commit()

        asyncio.run(reset_rows())
        self.session_id = self._seed_standalone_session()

    def _seed_standalone_session(self) -> str:
        session_id = str(uuid4())
        agent_id = str(uuid4())

        async def seed_rows() -> None:
            async with self.session_factory() as session:
                session.add(User(id=self.current_user_id, email=self.current_email))
                session.add(
                    Agent(
                        id=agent_id,
                        owner_user_id=self.current_user_id,
                        agent_key="solo",
                        name="Solo",
                        model_alias="deepseek",
                        role_prompt="Help user",
                        tool_permissions_json="[]",
                    )
                )
                session.add(
                    Session(
                        id=session_id,
                        room_id=None,
                        agent_id=agent_id,
                        started_by_user_id=self.current_user_id,
                    )
                )
                await session.commit()

        asyncio.run(seed_rows())
        return session_id

    def test_turn_rate_limit_per_minute(self) -> None:
        now = 1_700_000_005
        minute_bucket = now // 60
        hour_bucket = now // 3600
        app.state.arq_redis = FakeRedisPool(
            counts={
                f"ratelimit:{self.current_user_id}:turns:{minute_bucket}": 10,
                f"ratelimit:{self.current_user_id}:turns:{hour_bucket}": 0,
            }
        )
        with patch("apps.api.app.api.v1.routes.sessions.time.time", return_value=now):
            response = self.client.post(
                f"/api/v1/sessions/{self.session_id}/turns",
                json={"message": "hello"},
            )
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["detail"]["detail"], "rate limit exceeded")
        expected_retry = max(1, 60 - (now % 60))
        self.assertEqual(response.json()["detail"]["retry_after_seconds"], expected_retry)
        self.assertEqual(response.headers.get("Retry-After"), str(expected_retry))

    def test_turn_rate_limit_per_hour(self) -> None:
        now = 1_700_000_005
        minute_bucket = now // 60
        hour_bucket = now // 3600
        app.state.arq_redis = FakeRedisPool(
            counts={
                f"ratelimit:{self.current_user_id}:turns:{minute_bucket}": 0,
                f"ratelimit:{self.current_user_id}:turns:{hour_bucket}": 60,
            }
        )
        with patch("apps.api.app.api.v1.routes.sessions.time.time", return_value=now):
            response = self.client.post(
                f"/api/v1/sessions/{self.session_id}/turns",
                json={"message": "hello"},
            )
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["detail"]["detail"], "rate limit exceeded")
        expected_retry = max(1, 3600 - (now % 3600))
        self.assertEqual(response.headers.get("Retry-After"), str(expected_retry))

    def test_turn_rate_limit_not_triggered_below_limit(self) -> None:
        now = 1_700_000_005
        minute_bucket = now // 60
        hour_bucket = now // 3600
        app.state.arq_redis = FakeRedisPool(
            counts={
                f"ratelimit:{self.current_user_id}:turns:{minute_bucket}": 5,
                f"ratelimit:{self.current_user_id}:turns:{hour_bucket}": 20,
            }
        )
        with patch("apps.api.app.api.v1.routes.sessions.time.time", return_value=now):
            response = self.client.post(
                f"/api/v1/sessions/{self.session_id}/turns",
                json={"message": "hello"},
            )
        self.assertEqual(response.status_code, 201)

    def test_streaming_turn_rate_limited(self) -> None:
        now = 1_700_000_005
        minute_bucket = now // 60
        hour_bucket = now // 3600
        app.state.arq_redis = FakeRedisPool(
            counts={
                f"ratelimit:{self.current_user_id}:turns:{minute_bucket}": 10,
                f"ratelimit:{self.current_user_id}:turns:{hour_bucket}": 0,
            }
        )
        with patch("apps.api.app.api.v1.routes.sessions.time.time", return_value=now):
            response = self.client.post(
                f"/api/v1/sessions/{self.session_id}/turns/stream",
                json={"message": "hello"},
            )
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["detail"]["detail"], "rate limit exceeded")
        expected_retry = max(1, 60 - (now % 60))
        self.assertEqual(response.headers.get("Retry-After"), str(expected_retry))

    def test_rate_limit_skipped_when_redis_unavailable(self) -> None:
        app.state.arq_redis = None
        response = self.client.post(
            f"/api/v1/sessions/{self.session_id}/turns",
            json={"message": "hello"},
        )
        self.assertEqual(response.status_code, 201)


if __name__ == "__main__":
    unittest.main()
