from __future__ import annotations

import asyncio
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from apps.api.app.db.models import Agent, Base, User
from apps.api.app.db.session import get_db
from apps.api.app.dependencies.auth import get_current_user
from apps.api.app.main import app


class AgentRoutesTests(unittest.TestCase):
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

        async def override_get_db():
            async with cls.session_factory() as session:
                yield session

        def override_current_user() -> dict[str, str]:
            return {"user_id": "user-a", "email": "user-a@example.com"}

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

    def _set_user(self, *, user_id: str, email: str) -> None:
        def override_current_user() -> dict[str, str]:
            return {"user_id": user_id, "email": email}

        app.dependency_overrides[get_current_user] = override_current_user

    def _seed_user(self, *, user_id: str, email: str) -> None:
        async def insert_row() -> None:
            async with self.session_factory() as session:
                if await session.get(User, user_id) is None:
                    session.add(User(id=user_id, email=email))
                    await session.commit()

        asyncio.run(insert_row())

    def setUp(self) -> None:
        self._set_user(user_id="user-a", email="user-a@example.com")

    def _seed_agent(
        self,
        *,
        owner_user_id: str,
        agent_key: str,
        name: str = "Seed Agent",
        model_alias: str = "deepseek",
        role_prompt: str = "Seed role",
        tool_permissions_json: str = "[]",
    ) -> str:
        agent_id = str(uuid4())
        self._seed_user(user_id=owner_user_id, email=f"{owner_user_id}@example.com")

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
                        tool_permissions_json=tool_permissions_json,
                    )
                )
                await session.commit()

        asyncio.run(insert_row())
        return agent_id

    def test_create_agent(self) -> None:
        response = self.client.post(
            "/api/v1/agents",
            json={
                "agent_key": "writer",
                "name": "Writer",
                "model_alias": "qwen",
                "role_prompt": "Write clearly.",
                "tool_permissions": ["search"],
            },
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["owner_user_id"], "user-a")
        self.assertEqual(body["agent_key"], "writer")
        self.assertEqual(body["tool_permissions"], ["search"])

    def test_create_agent_duplicate_key_rejected(self) -> None:
        first = self.client.post(
            "/api/v1/agents",
            json={
                "agent_key": "researcher",
                "name": "Researcher",
                "model_alias": "deepseek",
                "role_prompt": "Research",
                "tool_permissions": [],
            },
        )
        self.assertEqual(first.status_code, 201)
        duplicate = self.client.post(
            "/api/v1/agents",
            json={
                "agent_key": "researcher",
                "name": "Researcher 2",
                "model_alias": "gpt-4o-mini",
                "role_prompt": "Research more",
                "tool_permissions": [],
            },
        )
        self.assertEqual(duplicate.status_code, 409)

    def test_list_agents_empty(self) -> None:
        self._set_user(user_id="user-empty", email="user-empty@example.com")
        response = self.client.get("/api/v1/agents")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["agents"], [])
        self.assertEqual(body["total"], 0)

    def test_list_agents_returns_own_only(self) -> None:
        self._seed_agent(owner_user_id="user-a", agent_key="a1")
        self._seed_agent(owner_user_id="user-b", agent_key="b1")
        response = self.client.get("/api/v1/agents")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertGreaterEqual(body["total"], 1)
        self.assertTrue(all(agent["owner_user_id"] == "user-a" for agent in body["agents"]))

    def test_get_agent(self) -> None:
        agent_id = self._seed_agent(owner_user_id="user-a", agent_key="getter")
        response = self.client.get(f"/api/v1/agents/{agent_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], agent_id)

    def test_get_agent_not_found(self) -> None:
        missing_id = str(uuid4())
        response = self.client.get(f"/api/v1/agents/{missing_id}")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Agent not found."})

    def test_update_agent(self) -> None:
        agent_id = self._seed_agent(owner_user_id="user-a", agent_key="updatable")
        response = self.client.patch(
            f"/api/v1/agents/{agent_id}",
            json={"name": "Updated Name", "tool_permissions": ["search", "file_read"]},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["name"], "Updated Name")
        self.assertEqual(body["tool_permissions"], ["search", "file_read"])

    def test_delete_agent(self) -> None:
        agent_id = self._seed_agent(owner_user_id="user-a", agent_key="deletable")
        delete_response = self.client.delete(f"/api/v1/agents/{agent_id}")
        self.assertEqual(delete_response.status_code, 204)

        get_response = self.client.get(f"/api/v1/agents/{agent_id}")
        self.assertEqual(get_response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
