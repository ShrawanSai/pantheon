from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
import json
import os
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Keep import-time settings self-contained for CI/local test runs.
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "dummy-service-role-key")
os.environ.setdefault("API_CORS_ALLOWED_ORIGINS", "http://localhost:3000")

from apps.api.app.db.models import (
    Base,
    CreditWallet,
    LlmCallEvent,
    Message,
    Room,
    RoomAgent,
    Session,
    ToolCallEvent,
    Turn,
    TurnContextAudit,
    User,
)
from apps.api.app.db.session import get_db
from apps.api.app.dependencies.auth import get_current_user
from apps.api.app.core.config import get_settings
from apps.api.app.main import app
from apps.api.app.services.llm.gateway import GatewayRequest, GatewayResponse, GatewayUsage, get_llm_gateway
from apps.api.app.services.orchestration.mode_executor import (
    ToolCallRecord,
    TurnExecutionInput,
    TurnExecutionOutput,
    get_mode_executor,
)
from apps.api.app.services.usage.recorder import UsageRecord, get_usage_recorder


@dataclass
class FakeGateway:
    calls: list[GatewayRequest] = field(default_factory=list)

    async def generate(self, request: GatewayRequest) -> GatewayResponse:
        self.calls.append(request)
        return GatewayResponse(
            text="This is a fake assistant response.",
            provider_model="fake/provider-model",
            usage=GatewayUsage(
                input_tokens_fresh=120,
                input_tokens_cached=0,
                output_tokens=40,
                total_tokens=160,
            ),
        )


@dataclass
class FakeUsageRecorder:
    records: list[UsageRecord] = field(default_factory=list)

    async def stage_llm_usage(self, db: AsyncSession, record: UsageRecord) -> None:
        _ = db
        self.records.append(record)

    async def record_llm_usage(self, db: AsyncSession, record: UsageRecord) -> None:
        await self.stage_llm_usage(db, record)


@dataclass
class FakeManagerGateway:
    response_text: str = "not json"
    calls: list[GatewayRequest] = field(default_factory=list)

    async def generate(self, request: GatewayRequest) -> GatewayResponse:
        self.calls.append(request)
        return GatewayResponse(
            text=self.response_text,
            provider_model="fake/manager-model",
            usage=GatewayUsage(
                input_tokens_fresh=3,
                input_tokens_cached=0,
                output_tokens=2,
                total_tokens=5,
            ),
        )


@dataclass
class FakeModeExecutor:
    gateway: FakeGateway

    async def run_turn(self, db: AsyncSession, payload: TurnExecutionInput) -> TurnExecutionOutput:
        _ = db
        response = await self.gateway.generate(
            GatewayRequest(
                model_alias=payload.model_alias,
                messages=payload.messages,
                max_output_tokens=payload.max_output_tokens,
            )
        )
        return TurnExecutionOutput(
            text=response.text,
            provider_model=response.provider_model,
            usage=response.usage,
        )


@dataclass
class PartialFailModeExecutor:
    gateway: FakeGateway
    fail_aliases: set[str] = field(default_factory=set)

    async def run_turn(self, db: AsyncSession, payload: TurnExecutionInput) -> TurnExecutionOutput:
        _ = db
        if payload.model_alias in self.fail_aliases:
            raise RuntimeError(f"forced failure for {payload.model_alias}")
        response = await self.gateway.generate(
            GatewayRequest(
                model_alias=payload.model_alias,
                messages=payload.messages,
                max_output_tokens=payload.max_output_tokens,
            )
        )
        return TurnExecutionOutput(
            text=response.text,
            provider_model=response.provider_model,
            usage=response.usage,
        )


class ConflictInjectingModeExecutor:
    async def run_turn(self, db: AsyncSession, payload: TurnExecutionInput) -> TurnExecutionOutput:
        session_id, turn_index_str, _ = payload.thread_id.split(":", 2)
        db.add(
            Turn(
                id=str(uuid4()),
                session_id=session_id,
                turn_index=int(turn_index_str),
                mode="orchestrator",
                user_input="conflict-seed",
                assistant_output="seed",
                status="completed",
            )
        )
        return TurnExecutionOutput(
            text="ok",
            provider_model="conflict/injector",
            usage=GatewayUsage(
                input_tokens_fresh=1,
                input_tokens_cached=0,
                output_tokens=1,
                total_tokens=2,
            ),
        )


class FakeToolTelemetryModeExecutor:
    async def run_turn(self, db: AsyncSession, payload: TurnExecutionInput) -> TurnExecutionOutput:
        _ = db
        tool_calls: tuple[ToolCallRecord, ...] = ()
        last_user = ""
        for message in payload.messages:
            if message.role == "user":
                last_user = message.content.strip().lower()
        if "search" in payload.allowed_tool_names and last_user.startswith("search:"):
            tool_calls = (
                ToolCallRecord(
                    tool_name="search",
                    input_json='{"query":"latest ai"}',
                    output_json='{"result_count":1}',
                    status="success",
                    latency_ms=42,
                ),
            )
        return TurnExecutionOutput(
            text="telemetry response",
            provider_model="fake/telemetry-model",
            usage=GatewayUsage(
                input_tokens_fresh=5,
                input_tokens_cached=0,
                output_tokens=3,
                total_tokens=8,
            ),
            tool_calls=tool_calls,
        )


class SessionTurnRoutesTests(unittest.TestCase):
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
        cls.fake_gateway = FakeGateway()
        cls.fake_manager_gateway = FakeManagerGateway()
        cls.fake_mode_executor = FakeModeExecutor(gateway=cls.fake_gateway)
        cls.fake_usage_recorder = FakeUsageRecorder()

        async def init_db() -> None:
            async with cls.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

        asyncio.run(init_db())

        async def override_get_db():
            async with cls.session_factory() as session:
                yield session

        def override_current_user() -> dict[str, str]:
            return {"user_id": "primary-user", "email": "primary-user@example.com"}

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_current_user
        app.dependency_overrides[get_llm_gateway] = lambda: cls.fake_manager_gateway
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
        self.fake_gateway.calls.clear()
        self.fake_manager_gateway.calls.clear()
        self.fake_manager_gateway.response_text = "not json"
        self.fake_usage_recorder.records.clear()
        os.environ.pop("CREDIT_ENFORCEMENT_ENABLED", None)
        get_settings.cache_clear()

    def tearDown(self) -> None:
        os.environ.pop("CREDIT_ENFORCEMENT_ENABLED", None)
        get_settings.cache_clear()

    def _seed_room(
        self,
        *,
        owner_user_id: str,
        owner_email: str,
        room_name: str,
        current_mode: str = "orchestrator",
        deleted_at: datetime | None = None,
    ) -> str:
        room_id = str(uuid4())

        async def insert_rows() -> None:
            async with self.session_factory() as session:
                user = await session.get(User, owner_user_id)
                if user is None:
                    session.add(User(id=owner_user_id, email=owner_email))
                session.add(
                    Room(
                        id=room_id,
                        owner_user_id=owner_user_id,
                        name=room_name,
                        goal="Test goal",
                        current_mode=current_mode,
                        pending_mode=None,
                        deleted_at=deleted_at,
                    )
                )
                await session.commit()

        asyncio.run(insert_rows())
        return room_id

    def _seed_agent(
        self,
        *,
        room_id: str,
        agent_key: str,
        model_alias: str = "deepseek",
        position: int = 1,
        tool_permissions: list[str] | None = None,
    ) -> None:
        permissions = tool_permissions or []

        async def insert_agent() -> None:
            async with self.session_factory() as session:
                session.add(
                    RoomAgent(
                        id=str(uuid4()),
                        room_id=room_id,
                        agent_key=agent_key,
                        name=agent_key.title(),
                        model_alias=model_alias,
                        role_prompt="Be helpful.",
                        tool_permissions_json=json.dumps(permissions),
                        position=position,
                    )
                )
                await session.commit()

        asyncio.run(insert_agent())

    def _seed_wallet(self, *, user_id: str, balance: Decimal) -> str:
        wallet_id = str(uuid4())

        async def insert_wallet() -> None:
            async with self.session_factory() as session:
                existing = await session.scalar(select(CreditWallet).where(CreditWallet.user_id == user_id))
                if existing is None:
                    session.add(
                        CreditWallet(
                            id=wallet_id,
                            user_id=user_id,
                            balance=balance,
                        )
                    )
                else:
                    existing.balance = balance
                await session.commit()

        asyncio.run(insert_wallet())
        return wallet_id

    def test_create_session_for_owned_room(self) -> None:
        room_id = self._seed_room(
            owner_user_id="primary-user",
            owner_email="primary-user@example.com",
            room_name="Session Room",
        )
        response = self.client.post(f"/api/v1/rooms/{room_id}/sessions")
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["room_id"], room_id)
        self.assertEqual(body["started_by_user_id"], "primary-user")

    def test_create_session_returns_404_for_not_owned_room(self) -> None:
        room_id = self._seed_room(
            owner_user_id="other-owner",
            owner_email="other-owner-session@example.com",
            room_name="Forbidden Session Room",
        )
        response = self.client.post(f"/api/v1/rooms/{room_id}/sessions")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Room not found."})

    def test_delete_session_soft_deletes_and_hides_from_list(self) -> None:
        room_id = self._seed_room(
            owner_user_id="primary-user",
            owner_email="primary-user@example.com",
            room_name="Delete Session Room",
        )
        create_response = self.client.post(f"/api/v1/rooms/{room_id}/sessions")
        session_id = create_response.json()["id"]

        delete_response = self.client.delete(f"/api/v1/rooms/{room_id}/sessions/{session_id}")
        self.assertEqual(delete_response.status_code, 204)

        list_response = self.client.get(f"/api/v1/rooms/{room_id}/sessions")
        self.assertEqual(list_response.status_code, 200)
        self.assertNotIn(session_id, {item["id"] for item in list_response.json()})

    def test_list_sessions_returns_only_owned_room_sessions(self) -> None:
        owned_room_id = self._seed_room(
            owner_user_id="primary-user",
            owner_email="primary-user@example.com",
            room_name="Owned Sessions Room",
        )
        other_room_id = self._seed_room(
            owner_user_id="other-owner",
            owner_email="other-owner-list@example.com",
            room_name="Other Owner Sessions Room",
        )

        owned_response = self.client.post(f"/api/v1/rooms/{owned_room_id}/sessions")
        self.assertEqual(owned_response.status_code, 201)
        owned_session_id = owned_response.json()["id"]

        other_response = self.client.post(f"/api/v1/rooms/{other_room_id}/sessions")
        self.assertEqual(other_response.status_code, 404)
        self.assertEqual(other_response.json(), {"detail": "Room not found."})

        list_response = self.client.get(f"/api/v1/rooms/{owned_room_id}/sessions")
        self.assertEqual(list_response.status_code, 200)
        sessions = list_response.json()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["id"], owned_session_id)
        self.assertEqual(sessions[0]["room_id"], owned_room_id)

    def test_delete_session_returns_404_for_not_owned_room(self) -> None:
        owned_room_id = self._seed_room(
            owner_user_id="primary-user",
            owner_email="primary-user@example.com",
            room_name="Owned Delete Session Room",
        )
        owned_session_response = self.client.post(f"/api/v1/rooms/{owned_room_id}/sessions")
        self.assertEqual(owned_session_response.status_code, 201)

        other_room_id = self._seed_room(
            owner_user_id="other-owner",
            owner_email="other-owner-delete@example.com",
            room_name="Other Owner Delete Session Room",
        )

        response = self.client.delete(
            f"/api/v1/rooms/{other_room_id}/sessions/{owned_session_response.json()['id']}"
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Room not found."})

    def test_create_turn_writes_turn_messages_and_audit(self) -> None:
        self.fake_gateway.calls.clear()
        self.fake_manager_gateway.calls.clear()
        self.fake_manager_gateway.response_text = "not json"
        self.fake_usage_recorder.records.clear()

        room_id = self._seed_room(
            owner_user_id="primary-user",
            owner_email="primary-user@example.com",
            room_name="Turn Room",
        )
        self._seed_agent(room_id=room_id, agent_key="researcher", model_alias="deepseek")
        session_response = self.client.post(f"/api/v1/rooms/{room_id}/sessions")
        session_id = session_response.json()["id"]

        turn_response = self.client.post(
            f"/api/v1/sessions/{session_id}/turns",
            json={"message": "Give me a quick summary."},
        )
        self.assertEqual(turn_response.status_code, 201)
        body = turn_response.json()
        self.assertEqual(body["session_id"], session_id)
        self.assertEqual(body["assistant_output"], "This is a fake assistant response.")
        self.assertFalse(body["overflow_rejected"])
        self.assertEqual(len(self.fake_gateway.calls), 1)
        self.assertEqual(len(self.fake_usage_recorder.records), 1)

        async def fetch_counts() -> tuple[int, int, int]:
            async with self.session_factory() as session:
                turns_count = int(await session.scalar(select(func.count(Turn.id)).where(Turn.session_id == session_id)) or 0)
                messages_count = int(
                    await session.scalar(select(func.count(Message.id)).where(Message.session_id == session_id)) or 0
                )
                audits_count = int(
                    await session.scalar(select(func.count(TurnContextAudit.id)).where(TurnContextAudit.session_id == session_id))
                    or 0
                )
                return turns_count, messages_count, audits_count

        turns_count, messages_count, audits_count = asyncio.run(fetch_counts())
        self.assertEqual(turns_count, 1)
        self.assertEqual(messages_count, 2)
        self.assertEqual(audits_count, 1)

    def test_turn_response_includes_balance_after(self) -> None:
        room_id = self._seed_room(
            owner_user_id="primary-user",
            owner_email="primary-user@example.com",
            room_name="Turn Balance Room",
        )
        self._seed_wallet(user_id="primary-user", balance=Decimal("10.0"))
        self._seed_agent(room_id=room_id, agent_key="researcher", model_alias="deepseek")
        session_response = self.client.post(f"/api/v1/rooms/{room_id}/sessions")
        self.assertEqual(session_response.status_code, 201)
        session_id = session_response.json()["id"]

        turn_response = self.client.post(
            f"/api/v1/sessions/{session_id}/turns",
            json={"message": "Check balance signal."},
        )
        self.assertEqual(turn_response.status_code, 201)
        body = turn_response.json()
        self.assertIsNotNone(body["balance_after"])
        self.assertFalse(body["low_balance"])

    def test_turn_response_low_balance_flag(self) -> None:
        room_id = self._seed_room(
            owner_user_id="primary-user",
            owner_email="primary-user@example.com",
            room_name="Turn Low Balance Room",
        )
        self._seed_wallet(user_id="primary-user", balance=Decimal("0.01"))
        self._seed_agent(room_id=room_id, agent_key="researcher", model_alias="deepseek")
        session_response = self.client.post(f"/api/v1/rooms/{room_id}/sessions")
        self.assertEqual(session_response.status_code, 201)
        session_id = session_response.json()["id"]

        turn_response = self.client.post(
            f"/api/v1/sessions/{session_id}/turns",
            json={"message": "Check low balance signal."},
        )
        self.assertEqual(turn_response.status_code, 201)
        body = turn_response.json()
        self.assertTrue(body["low_balance"])
        self.assertIsNotNone(body["balance_after"])

    def test_turn_rejected_when_enforcement_enabled_and_zero_balance(self) -> None:
        os.environ["CREDIT_ENFORCEMENT_ENABLED"] = "true"
        get_settings.cache_clear()
        self.addCleanup(lambda: (os.environ.pop("CREDIT_ENFORCEMENT_ENABLED", None), get_settings.cache_clear()))
        room_id = self._seed_room(
            owner_user_id="primary-user",
            owner_email="primary-user@example.com",
            room_name="Enforcement Enabled Room",
        )
        self._seed_wallet(user_id="primary-user", balance=Decimal("0.0"))
        self._seed_agent(room_id=room_id, agent_key="researcher", model_alias="deepseek")
        session_response = self.client.post(f"/api/v1/rooms/{room_id}/sessions")
        self.assertEqual(session_response.status_code, 201)
        session_id = session_response.json()["id"]

        turn_response = self.client.post(
            f"/api/v1/sessions/{session_id}/turns",
            json={"message": "This should be blocked."},
        )
        self.assertEqual(turn_response.status_code, 402)
        self.assertEqual(
            turn_response.json(),
            {"detail": "Insufficient credits. Please top up your account."},
        )

    def test_turn_allowed_when_enforcement_disabled_and_zero_balance(self) -> None:
        os.environ["CREDIT_ENFORCEMENT_ENABLED"] = "false"
        get_settings.cache_clear()
        self.addCleanup(lambda: (os.environ.pop("CREDIT_ENFORCEMENT_ENABLED", None), get_settings.cache_clear()))
        room_id = self._seed_room(
            owner_user_id="primary-user",
            owner_email="primary-user@example.com",
            room_name="Enforcement Disabled Room",
        )
        self._seed_wallet(user_id="primary-user", balance=Decimal("0.0"))
        self._seed_agent(room_id=room_id, agent_key="researcher", model_alias="deepseek")
        session_response = self.client.post(f"/api/v1/rooms/{room_id}/sessions")
        self.assertEqual(session_response.status_code, 201)
        session_id = session_response.json()["id"]

        turn_response = self.client.post(
            f"/api/v1/sessions/{session_id}/turns",
            json={"message": "This should still proceed."},
        )
        self.assertEqual(turn_response.status_code, 201)

    def test_create_second_turn_increments_turn_index_and_message_count(self) -> None:
        self.fake_gateway.calls.clear()
        self.fake_manager_gateway.calls.clear()
        self.fake_manager_gateway.response_text = "not json"
        self.fake_usage_recorder.records.clear()

        room_id = self._seed_room(
            owner_user_id="primary-user",
            owner_email="primary-user@example.com",
            room_name="Second Turn Room",
        )
        self._seed_agent(room_id=room_id, agent_key="writer", model_alias="deepseek")
        session_response = self.client.post(f"/api/v1/rooms/{room_id}/sessions")
        self.assertEqual(session_response.status_code, 201)
        session_id = session_response.json()["id"]

        first_turn = self.client.post(
            f"/api/v1/sessions/{session_id}/turns",
            json={"message": "First turn"},
        )
        self.assertEqual(first_turn.status_code, 201)
        self.assertEqual(first_turn.json()["turn_index"], 1)

        second_turn = self.client.post(
            f"/api/v1/sessions/{session_id}/turns",
            json={"message": "Second turn"},
        )
        self.assertEqual(second_turn.status_code, 201)
        self.assertEqual(second_turn.json()["turn_index"], 2)

        async def fetch_counts() -> tuple[int, int]:
            async with self.session_factory() as session:
                turns_count = int(await session.scalar(select(func.count(Turn.id)).where(Turn.session_id == session_id)) or 0)
                messages_count = int(
                    await session.scalar(select(func.count(Message.id)).where(Message.session_id == session_id)) or 0
                )
                return turns_count, messages_count

        turns_count, messages_count = asyncio.run(fetch_counts())
        self.assertEqual(turns_count, 2)
        self.assertEqual(messages_count, 4)

    def test_create_turn_returns_422_when_context_budget_exceeded(self) -> None:
        room_id = self._seed_room(
            owner_user_id="primary-user",
            owner_email="primary-user@example.com",
            room_name="Overflow Room",
        )
        self._seed_agent(room_id=room_id, agent_key="overflow_agent", model_alias="deepseek")
        session_response = self.client.post(f"/api/v1/rooms/{room_id}/sessions")
        session_id = session_response.json()["id"]

        huge_message = "x" * 50000
        response = self.client.post(
            f"/api/v1/sessions/{session_id}/turns",
            json={"message": huge_message},
        )
        self.assertEqual(response.status_code, 422)
        detail = response.json()["detail"]
        self.assertEqual(detail["code"], "context_budget_exceeded")
        self.assertEqual(len(self.fake_gateway.calls), 0)

    def test_create_turn_persists_llm_call_event_with_pricing_version(self) -> None:
        self.fake_gateway.calls.clear()
        self.fake_manager_gateway.calls.clear()
        self.fake_manager_gateway.response_text = "not json"

        # Use real UsageRecorder for this test to validate llm_call_events persistence.
        app.dependency_overrides.pop(get_usage_recorder, None)
        try:
            room_id = self._seed_room(
                owner_user_id="primary-user",
                owner_email="primary-user@example.com",
                room_name="Ledger Room",
            )
            self._seed_agent(room_id=room_id, agent_key="ledger_agent", model_alias="deepseek")
            session_response = self.client.post(f"/api/v1/rooms/{room_id}/sessions")
            self.assertEqual(session_response.status_code, 201)
            session_id = session_response.json()["id"]

            turn_response = self.client.post(
                f"/api/v1/sessions/{session_id}/turns",
                json={"message": "Persist usage event."},
            )
            self.assertEqual(turn_response.status_code, 201)

            async def fetch_event() -> LlmCallEvent | None:
                async with self.session_factory() as session:
                    return await session.scalar(
                        select(LlmCallEvent)
                        .where(LlmCallEvent.session_id == session_id)
                        .order_by(LlmCallEvent.created_at.desc())
                    )

            event = asyncio.run(fetch_event())
            self.assertIsNotNone(event)
            assert event is not None
            self.assertEqual(event.model_alias, "deepseek")
            self.assertEqual(event.provider, "openrouter")
            self.assertEqual(event.pricing_version, "2026-02-20")
            self.assertEqual(event.room_id, room_id)
            self.assertEqual(event.status, "success")
        finally:
            app.dependency_overrides[get_usage_recorder] = lambda: self.fake_usage_recorder

    def test_create_turn_usage_committed_atomically_with_turn(self) -> None:
        app.dependency_overrides.pop(get_usage_recorder, None)
        try:
            room_id = self._seed_room(
                owner_user_id="primary-user",
                owner_email="primary-user@example.com",
                room_name="Atomic Billing Room",
                current_mode="orchestrator",
            )
            self._seed_agent(room_id=room_id, agent_key="atomic_agent", model_alias="deepseek")
            session_response = self.client.post(f"/api/v1/rooms/{room_id}/sessions")
            self.assertEqual(session_response.status_code, 201)
            session_id = session_response.json()["id"]

            turn_response = self.client.post(
                f"/api/v1/sessions/{session_id}/turns",
                json={"message": "Atomically persist usage + turn."},
            )
            self.assertEqual(turn_response.status_code, 201)
            turn_id = turn_response.json()["id"]

            async def fetch_turn_and_events() -> tuple[Turn | None, int]:
                async with self.session_factory() as session:
                    turn = await session.get(Turn, turn_id)
                    events_count = int(
                        await session.scalar(select(func.count(LlmCallEvent.id)).where(LlmCallEvent.turn_id == turn_id))
                        or 0
                    )
                    return turn, events_count

            turn, events_count = asyncio.run(fetch_turn_and_events())
            self.assertIsNotNone(turn)
            self.assertEqual(events_count, 1)
        finally:
            app.dependency_overrides[get_usage_recorder] = lambda: self.fake_usage_recorder

    def test_create_turn_persists_tool_call_events_for_search_turn(self) -> None:
        app.dependency_overrides[get_mode_executor] = lambda: FakeToolTelemetryModeExecutor()
        try:
            room_id = self._seed_room(
                owner_user_id="primary-user",
                owner_email="primary-user@example.com",
                room_name="Tool Telemetry Room",
                current_mode="manual",
            )
            self._seed_agent(
                room_id=room_id,
                agent_key="researcher",
                model_alias="deepseek",
                tool_permissions=["search"],
            )
            session_response = self.client.post(f"/api/v1/rooms/{room_id}/sessions")
            self.assertEqual(session_response.status_code, 201)
            session_id = session_response.json()["id"]

            turn_response = self.client.post(
                f"/api/v1/sessions/{session_id}/turns",
                json={"message": "search: latest ai @researcher"},
            )
            self.assertEqual(turn_response.status_code, 201)
            turn_id = turn_response.json()["id"]

            async def fetch_tool_events() -> list[ToolCallEvent]:
                async with self.session_factory() as session:
                    rows = await session.scalars(
                        select(ToolCallEvent)
                        .where(ToolCallEvent.turn_id == turn_id)
                        .order_by(ToolCallEvent.created_at.asc())
                    )
                    return list(rows.all())

            events = asyncio.run(fetch_tool_events())
            self.assertEqual(len(events), 1)
            event = events[0]
            self.assertEqual(event.tool_name, "search")
            self.assertEqual(event.status, "success")
            self.assertEqual(event.session_id, session_id)
            self.assertEqual(event.agent_key, "researcher")
            self.assertEqual(event.credits_charged, 0)
            self.assertEqual(json.loads(event.tool_input_json)["query"], "latest ai")
            self.assertEqual(json.loads(event.tool_output_json)["result_count"], 1)
        finally:
            app.dependency_overrides[get_mode_executor] = lambda: self.fake_mode_executor

    def test_manual_mode_dispatches_only_tagged_agent(self) -> None:
        self.fake_gateway.calls.clear()
        room_id = self._seed_room(
            owner_user_id="primary-user",
            owner_email="primary-user@example.com",
            room_name="Manual Tagged Room",
            current_mode="manual",
        )
        self._seed_agent(room_id=room_id, agent_key="researcher", model_alias="deepseek")
        self._seed_agent(room_id=room_id, agent_key="writer", model_alias="qwen")
        session_response = self.client.post(f"/api/v1/rooms/{room_id}/sessions")
        self.assertEqual(session_response.status_code, 201)
        session_id = session_response.json()["id"]

        turn_response = self.client.post(
            f"/api/v1/sessions/{session_id}/turns",
            json={"message": "Please draft this @writer"},
        )
        self.assertEqual(turn_response.status_code, 201)
        self.assertEqual(turn_response.json()["model_alias_used"], "qwen")
        self.assertEqual(len(self.fake_gateway.calls), 1)
        self.assertEqual(self.fake_gateway.calls[0].model_alias, "qwen")

    def test_manual_mode_rejects_untagged_message(self) -> None:
        self.fake_gateway.calls.clear()
        room_id = self._seed_room(
            owner_user_id="primary-user",
            owner_email="primary-user@example.com",
            room_name="Manual Untagged Room",
            current_mode="manual",
        )
        self._seed_agent(room_id=room_id, agent_key="writer", model_alias="qwen")
        session_response = self.client.post(f"/api/v1/rooms/{room_id}/sessions")
        self.assertEqual(session_response.status_code, 201)
        session_id = session_response.json()["id"]

        response = self.client.post(
            f"/api/v1/sessions/{session_id}/turns",
            json={"message": "Please draft this"},
        )
        self.assertEqual(response.status_code, 422)
        detail = response.json()["detail"]
        self.assertEqual(detail["code"], "no_valid_tagged_agents")
        self.assertEqual(len(self.fake_gateway.calls), 0)

    def test_manual_mode_rejects_unknown_tag(self) -> None:
        self.fake_gateway.calls.clear()
        room_id = self._seed_room(
            owner_user_id="primary-user",
            owner_email="primary-user@example.com",
            room_name="Manual Unknown Tag Room",
            current_mode="manual",
        )
        self._seed_agent(room_id=room_id, agent_key="writer", model_alias="qwen")
        session_response = self.client.post(f"/api/v1/rooms/{room_id}/sessions")
        self.assertEqual(session_response.status_code, 201)
        session_id = session_response.json()["id"]

        response = self.client.post(
            f"/api/v1/sessions/{session_id}/turns",
            json={"message": "Please draft this @ghost"},
        )
        self.assertEqual(response.status_code, 422)
        detail = response.json()["detail"]
        self.assertEqual(detail["code"], "no_valid_tagged_agents")
        self.assertEqual(len(self.fake_gateway.calls), 0)

    def test_manual_mode_with_multiple_tags_dispatches_all_valid_tags_in_order(self) -> None:
        self.fake_gateway.calls.clear()
        room_id = self._seed_room(
            owner_user_id="primary-user",
            owner_email="primary-user@example.com",
            room_name="Manual Multi Tag Room",
            current_mode="manual",
        )
        self._seed_agent(room_id=room_id, agent_key="writer", model_alias="qwen")
        self._seed_agent(room_id=room_id, agent_key="researcher", model_alias="deepseek")
        session_response = self.client.post(f"/api/v1/rooms/{room_id}/sessions")
        self.assertEqual(session_response.status_code, 201)
        session_id = session_response.json()["id"]

        response = self.client.post(
            f"/api/v1/sessions/{session_id}/turns",
            json={"message": "Please collaborate @writer then @researcher"},
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["model_alias_used"], "qwen")
        self.assertEqual(body["status"], "completed")
        self.assertEqual([call.model_alias for call in self.fake_gateway.calls], ["qwen", "deepseek"])
        self.assertIn("Writer:", body["assistant_output"])
        self.assertIn("Researcher:", body["assistant_output"])

    def test_roundtable_mode_dispatches_agents_in_position_order(self) -> None:
        self.fake_gateway.calls.clear()
        room_id = self._seed_room(
            owner_user_id="primary-user",
            owner_email="primary-user@example.com",
            room_name="Roundtable Ordered Room",
            current_mode="roundtable",
        )
        self._seed_agent(room_id=room_id, agent_key="writer", model_alias="qwen", position=1)
        self._seed_agent(room_id=room_id, agent_key="researcher", model_alias="deepseek", position=2)
        self._seed_agent(room_id=room_id, agent_key="reviewer", model_alias="gpt_oss", position=3)
        session_response = self.client.post(f"/api/v1/rooms/{room_id}/sessions")
        self.assertEqual(session_response.status_code, 201)
        session_id = session_response.json()["id"]

        turn_response = self.client.post(
            f"/api/v1/sessions/{session_id}/turns",
            json={"message": "Discuss this proposal."},
        )
        self.assertEqual(turn_response.status_code, 201)
        self.assertEqual([call.model_alias for call in self.fake_gateway.calls], ["qwen", "deepseek", "gpt_oss"])

    def test_roundtable_mode_full_success_writes_all_assistant_messages(self) -> None:
        self.fake_gateway.calls.clear()
        room_id = self._seed_room(
            owner_user_id="primary-user",
            owner_email="primary-user@example.com",
            room_name="Roundtable Full Success Room",
            current_mode="roundtable",
        )
        self._seed_agent(room_id=room_id, agent_key="writer", model_alias="qwen", position=1)
        self._seed_agent(room_id=room_id, agent_key="researcher", model_alias="deepseek", position=2)
        self._seed_agent(room_id=room_id, agent_key="reviewer", model_alias="gpt_oss", position=3)
        session_response = self.client.post(f"/api/v1/rooms/{room_id}/sessions")
        self.assertEqual(session_response.status_code, 201)
        session_id = session_response.json()["id"]

        turn_response = self.client.post(
            f"/api/v1/sessions/{session_id}/turns",
            json={"message": "Debate pros and cons."},
        )
        self.assertEqual(turn_response.status_code, 201)
        body = turn_response.json()
        self.assertEqual(body["status"], "completed")
        self.assertEqual(body["mode"], "roundtable")
        self.assertTrue(body["assistant_output"].startswith("Writer: "))
        self.assertIn("Researcher:", body["assistant_output"])
        self.assertIn("Reviewer:", body["assistant_output"])
        self.assertEqual([call.model_alias for call in self.fake_gateway.calls], ["qwen", "deepseek", "gpt_oss"])

        async def fetch_roundtable_message_rows() -> list[tuple[str, str]]:
            async with self.session_factory() as session:
                rows = await session.execute(
                    select(Message.agent_name, Message.content)
                    .where(
                        Message.session_id == session_id,
                        Message.role == "assistant",
                        Message.mode == "roundtable",
                    )
                    .order_by(Message.created_at.asc(), Message.id.asc())
                )
                return [(name, content) for name, content in rows.all()]

        assistant_rows = asyncio.run(fetch_roundtable_message_rows())
        self.assertEqual(len(assistant_rows), 3)
        self.assertEqual({row[0] for row in assistant_rows}, {"Writer", "Researcher", "Reviewer"})

    def test_roundtable_mode_partial_failure_continues_remaining_agents(self) -> None:
        self.fake_gateway.calls.clear()
        room_id = self._seed_room(
            owner_user_id="primary-user",
            owner_email="primary-user@example.com",
            room_name="Roundtable Partial Room",
            current_mode="roundtable",
        )
        self._seed_agent(room_id=room_id, agent_key="writer", model_alias="qwen", position=1)
        self._seed_agent(room_id=room_id, agent_key="researcher", model_alias="deepseek", position=2)
        self._seed_agent(room_id=room_id, agent_key="reviewer", model_alias="gpt_oss", position=3)
        session_response = self.client.post(f"/api/v1/rooms/{room_id}/sessions")
        self.assertEqual(session_response.status_code, 201)
        session_id = session_response.json()["id"]

        failing_executor = PartialFailModeExecutor(gateway=self.fake_gateway, fail_aliases={"deepseek"})
        app.dependency_overrides[get_mode_executor] = lambda: failing_executor
        try:
            turn_response = self.client.post(
                f"/api/v1/sessions/{session_id}/turns",
                json={"message": "Roundtable with one failing agent."},
            )
            self.assertEqual(turn_response.status_code, 201)
            body = turn_response.json()
            self.assertEqual(body["status"], "partial")
            self.assertEqual([call.model_alias for call in self.fake_gateway.calls], ["qwen", "gpt_oss"])

            async def fetch_assistant_contents() -> list[str]:
                async with self.session_factory() as session:
                    rows = await session.scalars(
                        select(Message.content)
                        .where(
                            Message.session_id == session_id,
                            Message.role == "assistant",
                            Message.mode == "roundtable",
                        )
                        .order_by(Message.created_at.asc(), Message.id.asc())
                    )
                    return list(rows.all())

            contents = asyncio.run(fetch_assistant_contents())
            self.assertEqual(len(contents), 3)
            self.assertTrue(any("[[agent_error]]" in content for content in contents))
        finally:
            app.dependency_overrides[get_mode_executor] = lambda: self.fake_mode_executor

    def test_create_turn_returns_409_on_duplicate_turn_index(self) -> None:
        self.fake_gateway.calls.clear()
        self.fake_manager_gateway.calls.clear()
        self.fake_manager_gateway.response_text = "not json"
        self.fake_usage_recorder.records.clear()
        room_id = self._seed_room(
            owner_user_id="primary-user",
            owner_email="primary-user@example.com",
            room_name="Conflict Room",
            current_mode="orchestrator",
        )
        self._seed_agent(room_id=room_id, agent_key="writer", model_alias="qwen")
        session_response = self.client.post(f"/api/v1/rooms/{room_id}/sessions")
        self.assertEqual(session_response.status_code, 201)
        session_id = session_response.json()["id"]

        app.dependency_overrides[get_mode_executor] = lambda: ConflictInjectingModeExecutor()
        try:
            response = self.client.post(
                f"/api/v1/sessions/{session_id}/turns",
                json={"message": "Trigger deterministic turn index conflict."},
            )
            self.assertEqual(response.status_code, 409)
            self.assertEqual(
                response.json(),
                {"detail": "Turn creation conflicted with concurrent writes. Please retry."},
            )
        finally:
            app.dependency_overrides[get_mode_executor] = lambda: self.fake_mode_executor

    def test_orchestrator_mode_routes_to_manager_selected_agent(self) -> None:
        self.fake_gateway.calls.clear()
        self.fake_manager_gateway.calls.clear()
        self.fake_manager_gateway.response_text = '{"selected_agent_key":"writer"}'
        room_id = self._seed_room(
            owner_user_id="primary-user",
            owner_email="primary-user@example.com",
            room_name="Orchestrator Routing Room",
            current_mode="orchestrator",
        )
        self._seed_agent(room_id=room_id, agent_key="researcher", model_alias="deepseek", position=1)
        self._seed_agent(room_id=room_id, agent_key="writer", model_alias="qwen", position=2)
        session_response = self.client.post(f"/api/v1/rooms/{room_id}/sessions")
        self.assertEqual(session_response.status_code, 201)
        session_id = session_response.json()["id"]

        response = self.client.post(
            f"/api/v1/sessions/{session_id}/turns",
            json={"message": "Need final polish on this draft."},
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["model_alias_used"], "qwen")
        self.assertEqual(len(self.fake_gateway.calls), 1)
        self.assertEqual(self.fake_gateway.calls[0].model_alias, "qwen")

    def test_orchestrator_mode_dispatches_manager_selected_agent_sequence(self) -> None:
        self.fake_gateway.calls.clear()
        self.fake_manager_gateway.calls.clear()
        self.fake_manager_gateway.response_text = '{"selected_agent_keys":["writer","researcher"]}'
        room_id = self._seed_room(
            owner_user_id="primary-user",
            owner_email="primary-user@example.com",
            room_name="Orchestrator Sequence Room",
            current_mode="orchestrator",
        )
        self._seed_agent(room_id=room_id, agent_key="writer", model_alias="qwen", position=1)
        self._seed_agent(room_id=room_id, agent_key="researcher", model_alias="deepseek", position=2)
        self._seed_agent(room_id=room_id, agent_key="reviewer", model_alias="gpt_oss", position=3)
        session_response = self.client.post(f"/api/v1/rooms/{room_id}/sessions")
        self.assertEqual(session_response.status_code, 201)
        session_id = session_response.json()["id"]

        response = self.client.post(
            f"/api/v1/sessions/{session_id}/turns",
            json={"message": "Plan then research this."},
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["model_alias_used"], "multi-agent")
        self.assertEqual(body["status"], "completed")
        self.assertEqual([call.model_alias for call in self.fake_gateway.calls], ["qwen", "deepseek"])
        self.assertIn("Writer:", body["assistant_output"])
        self.assertIn("Researcher:", body["assistant_output"])
        turn_id = body["id"]

        async def fetch_audit_model_alias() -> str | None:
            async with self.session_factory() as session:
                return await session.scalar(
                    select(TurnContextAudit.model_alias).where(TurnContextAudit.turn_id == turn_id)
                )

        self.assertEqual(asyncio.run(fetch_audit_model_alias()), "multi-agent")

    def test_orchestrator_mode_partial_failure_continues_remaining_agents(self) -> None:
        self.fake_gateway.calls.clear()
        self.fake_manager_gateway.calls.clear()
        self.fake_manager_gateway.response_text = '{"selected_agent_keys":["writer","researcher","reviewer"]}'
        room_id = self._seed_room(
            owner_user_id="primary-user",
            owner_email="primary-user@example.com",
            room_name="Orchestrator Partial Room",
            current_mode="orchestrator",
        )
        self._seed_agent(room_id=room_id, agent_key="writer", model_alias="qwen", position=1)
        self._seed_agent(room_id=room_id, agent_key="researcher", model_alias="deepseek", position=2)
        self._seed_agent(room_id=room_id, agent_key="reviewer", model_alias="gpt_oss", position=3)
        session_response = self.client.post(f"/api/v1/rooms/{room_id}/sessions")
        self.assertEqual(session_response.status_code, 201)
        session_id = session_response.json()["id"]

        failing_executor = PartialFailModeExecutor(gateway=self.fake_gateway, fail_aliases={"deepseek"})
        app.dependency_overrides[get_mode_executor] = lambda: failing_executor
        try:
            response = self.client.post(
                f"/api/v1/sessions/{session_id}/turns",
                json={"message": "Draft, research, then review this."},
            )
            self.assertEqual(response.status_code, 201)
            body = response.json()
            self.assertEqual(body["model_alias_used"], "multi-agent")
            self.assertEqual(body["status"], "partial")
            self.assertIn("Writer:", body["assistant_output"])
            self.assertIn("Researcher:", body["assistant_output"])
            self.assertIn("Reviewer:", body["assistant_output"])
            self.assertIn("[[agent_error]]", body["assistant_output"])
            self.assertEqual(
                [call.model_alias for call in self.fake_gateway.calls],
                ["qwen", "gpt_oss"],
            )
        finally:
            app.dependency_overrides[get_mode_executor] = lambda: self.fake_mode_executor


if __name__ == "__main__":
    unittest.main()
