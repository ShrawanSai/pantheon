from __future__ import annotations

import asyncio
import os
import unittest
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Keep import-time settings self-contained for CI/local test runs.
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "dummy-service-role-key")
os.environ.setdefault("API_CORS_ALLOWED_ORIGINS", "http://localhost:3000")

from apps.api.app.db.models import Base, Room, UploadedFile, User
from apps.api.app.services.tools.file_tool import DefaultFileReadTool


class FileReadToolTests(unittest.TestCase):
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
        cls.tool = DefaultFileReadTool()

        async def init_db() -> None:
            async with cls.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

        asyncio.run(init_db())

    @classmethod
    def tearDownClass(cls) -> None:
        async def shutdown_db() -> None:
            async with cls.engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            await cls.engine.dispose()

        asyncio.run(shutdown_db())

    def _seed_uploaded_file(
        self,
        *,
        room_id: str | None = None,
        parse_status: str = "pending",
        parsed_text: str | None = None,
        error_message: str | None = None,
    ) -> tuple[str, str]:
        file_id = str(uuid4())
        effective_room_id = room_id or str(uuid4())
        user_id = str(uuid4())

        async def insert_rows() -> None:
            async with self.session_factory() as session:
                session.add(User(id=user_id, email=f"{user_id}@example.com"))
                session.add(
                    Room(
                        id=effective_room_id,
                        owner_user_id=user_id,
                        name="File Tool Room",
                        goal=None,
                        current_mode="orchestrator",
                        pending_mode=None,
                    )
                )
                session.add(
                    UploadedFile(
                        id=file_id,
                        user_id=user_id,
                        room_id=effective_room_id,
                        filename="notes.txt",
                        storage_key=f"rooms/{effective_room_id}/{file_id}/notes.txt",
                        content_type="text/plain",
                        file_size=12,
                        parse_status=parse_status,
                        parsed_text=parsed_text,
                        error_message=error_message,
                    )
                )
                await session.commit()

        asyncio.run(insert_rows())
        return file_id, effective_room_id

    def test_read_returns_completed_content(self) -> None:
        file_id, room_id = self._seed_uploaded_file(parse_status="completed", parsed_text="final parsed text")

        async def run_read():
            async with self.session_factory() as session:
                return await self.tool.read(file_id=file_id, room_id=room_id, db=session)

        result = asyncio.run(run_read())
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.content, "final parsed text")
        self.assertIsNone(result.error)

    def test_read_returns_pending_error(self) -> None:
        file_id, room_id = self._seed_uploaded_file(parse_status="pending")

        async def run_read():
            async with self.session_factory() as session:
                return await self.tool.read(file_id=file_id, room_id=room_id, db=session)

        result = asyncio.run(run_read())
        self.assertEqual(result.status, "pending")
        self.assertIsNone(result.content)
        self.assertEqual(result.error, "File is still being processed.")

    def test_read_returns_failed_error(self) -> None:
        file_id, room_id = self._seed_uploaded_file(parse_status="failed", error_message="parser failed")

        async def run_read():
            async with self.session_factory() as session:
                return await self.tool.read(file_id=file_id, room_id=room_id, db=session)

        result = asyncio.run(run_read())
        self.assertEqual(result.status, "failed")
        self.assertIsNone(result.content)
        self.assertEqual(result.error, "parser failed")

    def test_read_returns_not_found_when_missing(self) -> None:
        room_id = str(uuid4())

        async def run_read():
            async with self.session_factory() as session:
                return await self.tool.read(file_id=str(uuid4()), room_id=room_id, db=session)

        result = asyncio.run(run_read())
        self.assertEqual(result.status, "not_found")
        self.assertIsNone(result.content)
        self.assertEqual(result.error, "File not found.")

    def test_read_returns_not_found_for_cross_room_access(self) -> None:
        file_id, room_id = self._seed_uploaded_file(parse_status="completed", parsed_text="secret text")
        other_room_id = str(uuid4())
        self.assertNotEqual(room_id, other_room_id)

        async def run_read():
            async with self.session_factory() as session:
                return await self.tool.read(file_id=file_id, room_id=other_room_id, db=session)

        result = asyncio.run(run_read())
        self.assertEqual(result.status, "not_found")
        self.assertIsNone(result.content)
        self.assertEqual(result.error, "File not found.")


if __name__ == "__main__":
    unittest.main()

