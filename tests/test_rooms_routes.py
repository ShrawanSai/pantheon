from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import json
import os
import unittest
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Keep import-time settings self-contained for CI/local test runs.
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "dummy-service-role-key")
os.environ.setdefault("API_CORS_ALLOWED_ORIGINS", "http://localhost:3000")

from apps.api.app.dependencies.auth import get_current_user
from apps.api.app.db.models import Base, Room, RoomAgent, UploadedFile, User
from apps.api.app.db.session import get_db
from apps.api.app.dependencies.arq import get_arq_redis
from apps.api.app.main import app
from apps.api.app.services.storage.supabase_storage import get_storage_service


@dataclass
class FakeStorageService:
    uploads: list[dict[str, object]] = field(default_factory=list)

    async def upload_bytes(
        self,
        *,
        storage_key: str,
        content: bytes,
        content_type: str,
    ) -> None:
        self.uploads.append(
            {
                "storage_key": storage_key,
                "content": content,
                "content_type": content_type,
                "file_size": len(content),
            }
        )


@dataclass
class FakeArqRedis:
    enqueued: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)

    async def enqueue_job(self, job_name: str, *args: object):
        self.enqueued.append((job_name, args))
        return {"job_id": str(uuid4())}


class RoomRoutesTests(unittest.TestCase):
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

        def override_auth_me() -> dict[str, str]:
            return {"user_id": "user-123", "email": "user@example.com"}

        cls.fake_storage = FakeStorageService()
        cls.fake_arq_redis = FakeArqRedis()

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_auth_me
        app.dependency_overrides[get_storage_service] = lambda: cls.fake_storage
        app.dependency_overrides[get_arq_redis] = lambda: cls.fake_arq_redis
        cls.client = TestClient(app)

    def _set_auth_override(self, user_id: str, email: str) -> None:
        def override_auth_me() -> dict[str, str]:
            return {"user_id": user_id, "email": email}

        app.dependency_overrides[get_current_user] = override_auth_me

    def _clear_auth_override(self) -> None:
        app.dependency_overrides.pop(get_current_user, None)

    def setUp(self) -> None:
        self.fake_storage.uploads.clear()
        self.fake_arq_redis.enqueued.clear()

    def _seed_user_and_room(
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
                existing_user = await session.get(User, owner_user_id)
                if existing_user is None:
                    session.add(User(id=owner_user_id, email=owner_email))
                session.add(
                    Room(
                        id=room_id,
                        owner_user_id=owner_user_id,
                        name=room_name,
                        goal="seed goal",
                        current_mode="orchestrator",
                        pending_mode=None,
                        deleted_at=deleted_at,
                    )
                )
                await session.commit()

        asyncio.run(insert_rows())
        return room_id

    def _seed_room_agent(
        self,
        *,
        room_id: str,
        agent_key: str,
        name: str = "Agent",
        model_alias: str = "deepseek",
        role_prompt: str = "Do work",
        position: int = 1,
        tool_permissions: list[str] | None = None,
    ) -> str:
        agent_id = str(uuid4())
        permissions = tool_permissions or []

        async def insert_agent() -> None:
            async with self.session_factory() as session:
                session.add(
                    RoomAgent(
                        id=agent_id,
                        room_id=room_id,
                        agent_key=agent_key,
                        name=name,
                        model_alias=model_alias,
                        role_prompt=role_prompt,
                        tool_permissions_json=json.dumps(permissions),
                        position=position,
                    )
                )
                await session.commit()

        asyncio.run(insert_agent())
        return agent_id

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.clear()

        async def shutdown_db() -> None:
            async with cls.engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            await cls.engine.dispose()

        asyncio.run(shutdown_db())

    def test_create_room_persists_user_and_room(self) -> None:
        response = self.client.post(
            "/api/v1/rooms",
            json={
                "name": "  Product Planning  ",
                "goal": "Coordinate the team plan.",
                "current_mode": "orchestrator",
            },
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["owner_user_id"], "user-123")
        self.assertEqual(body["name"], "Product Planning")
        self.assertEqual(body["current_mode"], "orchestrator")
        room_id = body["id"]

        async def fetch_rows() -> tuple[User | None, Room | None]:
            async with self.session_factory() as session:
                user = await session.get(User, "user-123")
                room = await session.get(Room, room_id)
                return user, room

        user, room = asyncio.run(fetch_rows())
        self.assertIsNotNone(user)
        self.assertEqual(user.email, "user@example.com")
        self.assertIsNotNone(room)
        self.assertEqual(room.name, "Product Planning")
        self.assertEqual(room.goal, "Coordinate the team plan.")

    def test_create_room_uses_default_mode(self) -> None:
        response = self.client.post(
            "/api/v1/rooms",
            json={
                "name": "Default Mode Room",
                "goal": "Uses default mode when omitted.",
            },
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["current_mode"], "orchestrator")
        self.assertIsNone(body["pending_mode"])

    def test_create_room_without_auth_header_returns_401(self) -> None:
        self._clear_auth_override()
        try:
            response = self.client.post(
                "/api/v1/rooms",
                json={
                    "name": "Should Fail",
                    "goal": "No auth header.",
                    "current_mode": "orchestrator",
                },
            )
        finally:
            self._set_auth_override("user-123", "user@example.com")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "Missing Bearer token."})

    def test_create_room_rejects_invalid_mode(self) -> None:
        response = self.client.post(
            "/api/v1/rooms",
            json={
                "name": "Bad Mode",
                "goal": "Invalid mode should be rejected.",
                "current_mode": "invalid_mode",
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_create_room_rejects_blank_name(self) -> None:
        response = self.client.post(
            "/api/v1/rooms",
            json={
                "name": "   ",
                "goal": "Blank name should be rejected.",
                "current_mode": "orchestrator",
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_list_rooms_returns_only_active_owned_rooms(self) -> None:
        owned_active = self._seed_user_and_room(
            owner_user_id="user-123",
            owner_email="user@example.com",
            room_name="Owned Active",
        )
        self._seed_user_and_room(
            owner_user_id="user-123",
            owner_email="user@example.com",
            room_name="Owned Deleted",
            deleted_at=datetime.now(timezone.utc),
        )
        self._seed_user_and_room(
            owner_user_id="other-user",
            owner_email="other@example.com",
            room_name="Other User Room",
        )

        response = self.client.get("/api/v1/rooms")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        room_ids = {row["id"] for row in body}
        self.assertIn(owned_active, room_ids)
        self.assertNotIn("Owned Deleted", {row["name"] for row in body})
        self.assertNotIn("Other User Room", {row["name"] for row in body})

    def test_get_room_by_id_returns_owned_room(self) -> None:
        room_id = self._seed_user_and_room(
            owner_user_id="user-123",
            owner_email="user@example.com",
            room_name="Read Target",
        )
        response = self.client.get(f"/api/v1/rooms/{room_id}")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["id"], room_id)
        self.assertEqual(body["name"], "Read Target")

    def test_get_room_by_id_returns_404_when_not_owned(self) -> None:
        room_id = self._seed_user_and_room(
            owner_user_id="other-user-2",
            owner_email="other2@example.com",
            room_name="Private Room",
        )
        response = self.client.get(f"/api/v1/rooms/{room_id}")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Room not found."})

    def test_get_room_by_id_returns_404_when_owned_but_deleted(self) -> None:
        room_id = self._seed_user_and_room(
            owner_user_id="user-123",
            owner_email="user@example.com",
            room_name="Owned Deleted Target",
            deleted_at=datetime.now(timezone.utc),
        )
        response = self.client.get(f"/api/v1/rooms/{room_id}")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Room not found."})

    def test_delete_room_soft_deletes_owned_room(self) -> None:
        room_id = self._seed_user_and_room(
            owner_user_id="user-123",
            owner_email="user@example.com",
            room_name="Delete Target",
        )
        delete_response = self.client.delete(f"/api/v1/rooms/{room_id}")
        self.assertEqual(delete_response.status_code, 204)

        async def fetch_deleted_marker() -> datetime | None:
            async with self.session_factory() as session:
                room = await session.get(Room, room_id)
                return None if room is None else room.deleted_at

        deleted_at = asyncio.run(fetch_deleted_marker())
        self.assertIsNotNone(deleted_at)

        get_response = self.client.get(f"/api/v1/rooms/{room_id}")
        self.assertEqual(get_response.status_code, 404)

        list_response = self.client.get("/api/v1/rooms")
        self.assertEqual(list_response.status_code, 200)
        self.assertNotIn(room_id, {row["id"] for row in list_response.json()})

    def test_delete_room_returns_404_when_not_owned(self) -> None:
        room_id = self._seed_user_and_room(
            owner_user_id="other-user-3",
            owner_email="other3@example.com",
            room_name="Other User Delete Target",
        )
        response = self.client.delete(f"/api/v1/rooms/{room_id}")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Room not found."})

    def test_delete_room_returns_404_when_already_deleted(self) -> None:
        room_id = self._seed_user_and_room(
            owner_user_id="user-123",
            owner_email="user@example.com",
            room_name="Already Deleted",
            deleted_at=datetime.now(timezone.utc),
        )
        response = self.client.delete(f"/api/v1/rooms/{room_id}")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Room not found."})

    def test_create_room_agent_persists_for_owned_room(self) -> None:
        room_id = self._seed_user_and_room(
            owner_user_id="user-123",
            owner_email="user@example.com",
            room_name="Agent Room",
        )
        response = self.client.post(
            f"/api/v1/rooms/{room_id}/agents",
            json={
                "agent_key": "researcher",
                "name": "Research Analyst",
                "model_alias": "deepseek",
                "role_prompt": "Find facts.",
                "tool_permissions": ["search", "fetch"],
            },
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["room_id"], room_id)
        self.assertEqual(body["agent_key"], "researcher")
        self.assertEqual(body["tool_permissions"], ["search", "fetch"])

    def test_create_room_agent_returns_409_on_duplicate_agent_key(self) -> None:
        room_id = self._seed_user_and_room(
            owner_user_id="user-123",
            owner_email="user@example.com",
            room_name="Duplicate Agent Room",
        )
        first = self.client.post(
            f"/api/v1/rooms/{room_id}/agents",
            json={
                "agent_key": "writer",
                "name": "Writer",
                "model_alias": "qwen",
                "role_prompt": "Write text.",
                "tool_permissions": [],
            },
        )
        self.assertEqual(first.status_code, 201)

        duplicate = self.client.post(
            f"/api/v1/rooms/{room_id}/agents",
            json={
                "agent_key": "writer",
                "name": "Writer 2",
                "model_alias": "llama",
                "role_prompt": "Write more text.",
                "tool_permissions": [],
            },
        )
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.json(), {"detail": "Agent key already exists in this room."})

    def test_create_room_agent_returns_404_for_not_owned_room(self) -> None:
        room_id = self._seed_user_and_room(
            owner_user_id="other-owner",
            owner_email="other-owner@example.com",
            room_name="Private Agent Room",
        )
        response = self.client.post(
            f"/api/v1/rooms/{room_id}/agents",
            json={
                "agent_key": "reviewer",
                "name": "Reviewer",
                "model_alias": "gpt_oss",
                "role_prompt": "Review work.",
                "tool_permissions": [],
            },
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Room not found."})

    def test_list_room_agents_returns_owned_room_agents(self) -> None:
        own_room_id = self._seed_user_and_room(
            owner_user_id="user-123",
            owner_email="user@example.com",
            room_name="Owned Agent List",
        )
        other_room_id = self._seed_user_and_room(
            owner_user_id="other-owner-2",
            owner_email="agents-other2@example.com",
            room_name="Other Agent List",
        )
        self._seed_room_agent(
            room_id=own_room_id,
            agent_key="researcher",
            name="Researcher",
            model_alias="deepseek",
            position=2,
            tool_permissions=["search"],
        )
        self._seed_room_agent(
            room_id=own_room_id,
            agent_key="writer",
            name="Writer",
            model_alias="qwen",
            position=1,
            tool_permissions=["fetch"],
        )
        self._seed_room_agent(
            room_id=other_room_id,
            agent_key="other",
            name="Other",
            model_alias="llama",
            position=1,
        )

        response = self.client.get(f"/api/v1/rooms/{own_room_id}/agents")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual([agent["agent_key"] for agent in body], ["writer", "researcher"])

    def test_list_room_agents_returns_404_for_not_owned_room(self) -> None:
        room_id = self._seed_user_and_room(
            owner_user_id="other-owner-3",
            owner_email="agents-other3@example.com",
            room_name="Forbidden List",
        )
        response = self.client.get(f"/api/v1/rooms/{room_id}/agents")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Room not found."})

    def test_delete_room_agent_removes_agent_from_owned_room(self) -> None:
        room_id = self._seed_user_and_room(
            owner_user_id="user-123",
            owner_email="user@example.com",
            room_name="Delete Agent Room",
        )
        self._seed_room_agent(
            room_id=room_id,
            agent_key="reviewer",
            name="Reviewer",
            model_alias="qwen",
            position=1,
        )

        response = self.client.delete(f"/api/v1/rooms/{room_id}/agents/reviewer")
        self.assertEqual(response.status_code, 204)

        list_response = self.client.get(f"/api/v1/rooms/{room_id}/agents")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json(), [])

    def test_delete_room_agent_returns_404_for_not_owned_room(self) -> None:
        room_id = self._seed_user_and_room(
            owner_user_id="other-owner-4",
            owner_email="other4@example.com",
            room_name="Other Owner Delete Agent",
        )
        self._seed_room_agent(
            room_id=room_id,
            agent_key="writer",
            name="Writer",
            model_alias="qwen",
            position=1,
        )
        response = self.client.delete(f"/api/v1/rooms/{room_id}/agents/writer")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Room not found."})

    def test_delete_room_agent_returns_404_when_agent_key_not_found(self) -> None:
        room_id = self._seed_user_and_room(
            owner_user_id="user-123",
            owner_email="user@example.com",
            room_name="No Agent Room",
        )
        response = self.client.delete(f"/api/v1/rooms/{room_id}/agents/nonexistent")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Agent not found."})

    def test_upload_room_file_persists_metadata_and_enqueues_parse_job(self) -> None:
        room_id = self._seed_user_and_room(
            owner_user_id="user-123",
            owner_email="user@example.com",
            room_name="File Upload Room",
        )
        response = self.client.post(
            f"/api/v1/rooms/{room_id}/files",
            files={"file": ("notes.txt", b"hello world", "text/plain")},
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["room_id"], room_id)
        self.assertEqual(body["filename"], "notes.txt")
        self.assertEqual(body["parse_status"], "pending")
        self.assertEqual(body["file_size"], 11)
        self.assertTrue(body["storage_key"].startswith(f"rooms/{room_id}/"))

        self.assertEqual(len(self.fake_storage.uploads), 1)
        upload = self.fake_storage.uploads[0]
        self.assertEqual(upload["content"], b"hello world")
        self.assertEqual(upload["content_type"], "text/plain")
        self.assertEqual(upload["file_size"], 11)

        self.assertEqual(len(self.fake_arq_redis.enqueued), 1)
        job_name, job_args = self.fake_arq_redis.enqueued[0]
        self.assertEqual(job_name, "file_parse")
        self.assertEqual(job_args[0], body["id"])

        async def fetch_file_row() -> UploadedFile | None:
            async with self.session_factory() as session:
                return await session.get(UploadedFile, body["id"])

        stored = asyncio.run(fetch_file_row())
        self.assertIsNotNone(stored)
        self.assertEqual(stored.filename, "notes.txt")
        self.assertEqual(stored.parse_status, "pending")

    def test_upload_room_file_returns_413_when_oversized(self) -> None:
        room_id = self._seed_user_and_room(
            owner_user_id="user-123",
            owner_email="user@example.com",
            room_name="Oversize File Room",
        )
        response = self.client.post(
            f"/api/v1/rooms/{room_id}/files",
            files={"file": ("big.txt", b"x" * 1_048_577, "text/plain")},
        )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json(), {"detail": "File exceeds maximum allowed size."})
        self.assertEqual(self.fake_storage.uploads, [])
        self.assertEqual(self.fake_arq_redis.enqueued, [])

    def test_upload_room_file_returns_422_for_invalid_format(self) -> None:
        room_id = self._seed_user_and_room(
            owner_user_id="user-123",
            owner_email="user@example.com",
            room_name="Invalid Format Room",
        )
        response = self.client.post(
            f"/api/v1/rooms/{room_id}/files",
            files={"file": ("report.pdf", b"%PDF-1.4", "application/pdf")},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json(),
            {"detail": "Unsupported file format. Allowed: txt, md, csv."},
        )
        self.assertEqual(self.fake_storage.uploads, [])
        self.assertEqual(self.fake_arq_redis.enqueued, [])

    def test_upload_room_file_returns_404_for_unowned_room(self) -> None:
        room_id = self._seed_user_and_room(
            owner_user_id="other-user",
            owner_email="other@example.com",
            room_name="Other User File Room",
        )
        response = self.client.post(
            f"/api/v1/rooms/{room_id}/files",
            files={"file": ("notes.txt", b"hello", "text/plain")},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Room not found."})
        self.assertEqual(self.fake_storage.uploads, [])
        self.assertEqual(self.fake_arq_redis.enqueued, [])


if __name__ == "__main__":
    unittest.main()
