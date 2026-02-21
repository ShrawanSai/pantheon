from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
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

from apps.api.app.db.models import Base, Message, Room, RoomAgent, Session, Turn, TurnContextAudit, User
from apps.api.app.db.session import get_db
from apps.api.app.dependencies.auth import get_current_user
from apps.api.app.main import app
from apps.api.app.services.llm.gateway import GatewayRequest, GatewayResponse, GatewayUsage, get_llm_gateway
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

    async def record_llm_usage(self, record: UsageRecord) -> None:
        self.records.append(record)


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
        app.dependency_overrides[get_llm_gateway] = lambda: cls.fake_gateway
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

    def _seed_room(
        self,
        *,
        owner_user_id: str,
        owner_email: str,
        room_name: str,
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
                        current_mode="orchestrator",
                        pending_mode=None,
                        deleted_at=deleted_at,
                    )
                )
                await session.commit()

        asyncio.run(insert_rows())
        return room_id

    def _seed_agent(self, *, room_id: str, agent_key: str, model_alias: str = "deepseek") -> None:
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
                        tool_permissions_json="[]",
                        position=1,
                    )
                )
                await session.commit()

        asyncio.run(insert_agent())

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

    def test_create_second_turn_increments_turn_index_and_message_count(self) -> None:
        self.fake_gateway.calls.clear()
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
        self.fake_gateway.calls.clear()
        room_id = self._seed_room(
            owner_user_id="primary-user",
            owner_email="primary-user@example.com",
            room_name="Overflow Room",
        )
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


if __name__ == "__main__":
    unittest.main()
