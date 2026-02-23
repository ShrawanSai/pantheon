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
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "dummy-service-role-key")
os.environ.setdefault("API_CORS_ALLOWED_ORIGINS", "http://localhost:3000")

from apps.api.app.db.models import (
    Agent,
    Base,
    CreditTransaction,
    CreditWallet,
    LlmCallEvent,
    Message,
    Room,
    RoomAgent,
    Session,
    SessionSummary,
    ToolCallEvent,
    Turn,
    TurnContextAudit,
    User,
)
from apps.api.app.db.session import get_db
from apps.api.app.dependencies.auth import get_current_user
from apps.api.app.main import app
from apps.api.app.services.llm.gateway import GatewayUsage, get_llm_gateway
from apps.api.app.services.orchestration.mode_executor import (
    TurnExecutionInput,
    TurnExecutionOutput,
    get_mode_executor,
)


@dataclass
class FakeManagerGateway:
    response_text: str = "not json"

    async def generate(self, request):
        _ = request
        return type(
            "Resp",
            (),
            {
                "text": self.response_text,
                "provider_model": "fake/manager",
                "usage": GatewayUsage(
                    input_tokens_fresh=1,
                    input_tokens_cached=0,
                    output_tokens=1,
                    total_tokens=2,
                ),
            },
        )()


@dataclass
class FakeModeExecutor:
    calls: list[TurnExecutionInput] = field(default_factory=list)

    async def run_turn(self, db: AsyncSession, payload: TurnExecutionInput) -> TurnExecutionOutput:
        _ = db
        self.calls.append(payload)
        user_texts = [msg.content for msg in payload.messages if msg.role == "user"]
        response_text = " | ".join(user_texts) if user_texts else "ok"
        return TurnExecutionOutput(
            text=response_text,
            provider_model="fake/standalone-model",
            usage=GatewayUsage(
                input_tokens_fresh=20,
                input_tokens_cached=0,
                output_tokens=10,
                total_tokens=30,
            ),
        )


class StandaloneSessionsTests(unittest.TestCase):
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
        cls.fake_manager_gateway = FakeManagerGateway()
        cls.fake_mode_executor = FakeModeExecutor()

        async def init_db() -> None:
            async with cls.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

        asyncio.run(init_db())

        async def override_get_db():
            async with cls.session_factory() as session:
                yield session

        def override_current_user() -> dict[str, str]:
            return {"user_id": "standalone-user", "email": "standalone@example.com"}

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_current_user
        app.dependency_overrides[get_llm_gateway] = lambda: cls.fake_manager_gateway
        app.dependency_overrides[get_mode_executor] = lambda: cls.fake_mode_executor
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.clear()

        async def shutdown_db() -> None:
            async with cls.engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            await cls.engine.dispose()

        asyncio.run(shutdown_db())

    def _set_user(self, *, user_id: str, email: str) -> None:
        def override_current_user() -> dict[str, str]:
            return {"user_id": user_id, "email": email}

        app.dependency_overrides[get_current_user] = override_current_user

    def setUp(self) -> None:
        self.fake_mode_executor.calls.clear()
        self._set_user(user_id="standalone-user", email="standalone@example.com")

        async def reset_rows() -> None:
            async with self.session_factory() as session:
                await session.execute(delete(ToolCallEvent))
                await session.execute(delete(LlmCallEvent))
                await session.execute(delete(TurnContextAudit))
                await session.execute(delete(Message))
                await session.execute(delete(SessionSummary))
                await session.execute(delete(Turn))
                await session.execute(delete(Session))
                await session.execute(delete(RoomAgent))
                await session.execute(delete(Agent))
                await session.execute(delete(CreditTransaction))
                await session.execute(delete(CreditWallet))
                await session.execute(delete(Room))
                await session.execute(delete(User))
                await session.commit()

        asyncio.run(reset_rows())

    def _seed_user(self, *, user_id: str, email: str) -> None:
        async def insert_row() -> None:
            async with self.session_factory() as session:
                session.add(User(id=user_id, email=email))
                await session.commit()

        asyncio.run(insert_row())

    def _seed_agent(
        self,
        *,
        owner_user_id: str,
        agent_key: str = "assistant",
        name: str = "Standalone Assistant",
        model_alias: str = "deepseek",
        role_prompt: str = "Be helpful.",
    ) -> str:
        self._seed_user(user_id=owner_user_id, email=f"{owner_user_id}@example.com")
        agent_id = str(uuid4())

        async def insert_row() -> None:
            async with self.session_factory() as session:
                session.add(
                    Agent(
                        id=agent_id,
                        owner_user_id=owner_user_id,
                        agent_key=agent_key,
                        name=name,
                        model_alias=model_alias,
                        role_prompt=role_prompt,
                        tool_permissions_json="[]",
                    )
                )
                await session.commit()

        asyncio.run(insert_row())
        return agent_id

    def _seed_room_with_assignment(self, *, owner_user_id: str) -> tuple[str, str]:
        self._seed_user(user_id=owner_user_id, email=f"{owner_user_id}@example.com")
        room_id = str(uuid4())
        agent_id = str(uuid4())

        async def insert_rows() -> None:
            async with self.session_factory() as session:
                session.add(
                    Room(
                        id=room_id,
                        owner_user_id=owner_user_id,
                        name="History Room",
                        goal="History checks.",
                        current_mode="orchestrator",
                        pending_mode=None,
                        deleted_at=None,
                    )
                )
                session.add(
                    Agent(
                        id=agent_id,
                        owner_user_id=owner_user_id,
                        agent_key="writer",
                        name="Writer",
                        model_alias="qwen",
                        role_prompt="Write clearly.",
                        tool_permissions_json=json.dumps(["search"]),
                    )
                )
                session.add(
                    RoomAgent(
                        id=str(uuid4()),
                        room_id=room_id,
                        agent_id=agent_id,
                        position=1,
                    )
                )
                await session.commit()

        asyncio.run(insert_rows())
        return room_id, agent_id

    def test_create_standalone_session(self) -> None:
        agent_id = self._seed_agent(owner_user_id="standalone-user")
        response = self.client.post(f"/api/v1/agents/{agent_id}/sessions")
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["agent_id"], agent_id)
        self.assertIsNone(body["room_id"])

    def test_list_standalone_sessions(self) -> None:
        agent_id = self._seed_agent(owner_user_id="standalone-user")
        first = self.client.post(f"/api/v1/agents/{agent_id}/sessions")
        self.assertEqual(first.status_code, 201)
        second = self.client.post(f"/api/v1/agents/{agent_id}/sessions")
        self.assertEqual(second.status_code, 201)

        response = self.client.get(f"/api/v1/agents/{agent_id}/sessions")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body), 2)
        self.assertTrue(all(item["agent_id"] == agent_id for item in body))

    def test_submit_turn_standalone_agent(self) -> None:
        agent_id = self._seed_agent(owner_user_id="standalone-user", model_alias="deepseek")
        session_response = self.client.post(f"/api/v1/agents/{agent_id}/sessions")
        session_id = session_response.json()["id"]

        turn_response = self.client.post(
            f"/api/v1/sessions/{session_id}/turns",
            json={"message": "Hello standalone"},
        )
        self.assertEqual(turn_response.status_code, 201)
        body = turn_response.json()
        self.assertEqual(body["mode"], "standalone")
        self.assertNotEqual(body["assistant_output"], "")

    def test_standalone_turn_records_usage(self) -> None:
        agent_id = self._seed_agent(owner_user_id="standalone-user")
        session_response = self.client.post(f"/api/v1/agents/{agent_id}/sessions")
        session_id = session_response.json()["id"]

        turn_response = self.client.post(
            f"/api/v1/sessions/{session_id}/turns",
            json={"message": "Track usage"},
        )
        self.assertEqual(turn_response.status_code, 201)
        turn_id = turn_response.json()["id"]

        async def fetch_event() -> LlmCallEvent | None:
            async with self.session_factory() as session:
                return await session.scalar(
                    select(LlmCallEvent)
                    .where(LlmCallEvent.turn_id == turn_id)
                    .order_by(LlmCallEvent.created_at.desc())
                )

        event = asyncio.run(fetch_event())
        self.assertIsNotNone(event)
        assert event is not None
        self.assertIsNone(event.room_id)
        self.assertEqual(event.agent_id, agent_id)

    def test_standalone_turn_context_carries_over(self) -> None:
        agent_id = self._seed_agent(owner_user_id="standalone-user")
        session_response = self.client.post(f"/api/v1/agents/{agent_id}/sessions")
        session_id = session_response.json()["id"]

        first = self.client.post(
            f"/api/v1/sessions/{session_id}/turns",
            json={"message": "First standalone message"},
        )
        self.assertEqual(first.status_code, 201)

        second = self.client.post(
            f"/api/v1/sessions/{session_id}/turns",
            json={"message": "Second standalone message"},
        )
        self.assertEqual(second.status_code, 201)
        self.assertIn("First standalone message", second.json()["assistant_output"])

    def test_get_session_messages_empty(self) -> None:
        agent_id = self._seed_agent(owner_user_id="standalone-user")
        session_response = self.client.post(f"/api/v1/agents/{agent_id}/sessions")
        session_id = session_response.json()["id"]

        response = self.client.get(f"/api/v1/sessions/{session_id}/messages")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["messages"], [])
        self.assertEqual(body["total"], 0)

    def test_get_session_messages_returns_history(self) -> None:
        room_id, _ = self._seed_room_with_assignment(owner_user_id="standalone-user")
        session_response = self.client.post(f"/api/v1/rooms/{room_id}/sessions")
        session_id = session_response.json()["id"]
        turn_response = self.client.post(
            f"/api/v1/sessions/{session_id}/turns",
            json={"message": "History please"},
        )
        self.assertEqual(turn_response.status_code, 201)

        response = self.client.get(f"/api/v1/sessions/{session_id}/messages")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 3)
        self.assertEqual([msg["role"] for msg in body["messages"]], ["user", "assistant", "assistant"])
        self.assertEqual(body["messages"][0]["content"], "History please")
        assistant_agent_names = [msg["agent_name"] for msg in body["messages"] if msg["role"] == "assistant"]
        self.assertIn("Manager", assistant_agent_names)

    def test_get_session_messages_standalone(self) -> None:
        agent_id = self._seed_agent(owner_user_id="standalone-user")
        session_response = self.client.post(f"/api/v1/agents/{agent_id}/sessions")
        session_id = session_response.json()["id"]
        turn_response = self.client.post(
            f"/api/v1/sessions/{session_id}/turns",
            json={"message": "Standalone history"},
        )
        self.assertEqual(turn_response.status_code, 201)

        response = self.client.get(f"/api/v1/sessions/{session_id}/messages")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 2)
        self.assertEqual(body["messages"][0]["content"], "Standalone history")

    def test_get_session_turns(self) -> None:
        room_id, _ = self._seed_room_with_assignment(owner_user_id="standalone-user")
        session_response = self.client.post(f"/api/v1/rooms/{room_id}/sessions")
        session_id = session_response.json()["id"]
        first = self.client.post(
            f"/api/v1/sessions/{session_id}/turns",
            json={"message": "Turn one"},
        )
        self.assertEqual(first.status_code, 201)
        second = self.client.post(
            f"/api/v1/sessions/{session_id}/turns",
            json={"message": "Turn two"},
        )
        self.assertEqual(second.status_code, 201)

        response = self.client.get(f"/api/v1/sessions/{session_id}/turns")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 2)
        self.assertEqual([turn["turn_index"] for turn in body["turns"]], [1, 2])

    def test_get_session_messages_ownership(self) -> None:
        agent_id = self._seed_agent(owner_user_id="standalone-user")
        session_response = self.client.post(f"/api/v1/agents/{agent_id}/sessions")
        session_id = session_response.json()["id"]

        self._seed_user(user_id="other-user", email="other-user@example.com")
        self._set_user(user_id="other-user", email="other-user@example.com")
        response = self.client.get(f"/api/v1/sessions/{session_id}/messages")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Session not found."})


if __name__ == "__main__":
    unittest.main()
