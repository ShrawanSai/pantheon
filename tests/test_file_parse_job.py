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
from apps.api.app.workers.jobs.file_parse import file_parse


class FileParseJobTests(unittest.TestCase):
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

    @classmethod
    def tearDownClass(cls) -> None:
        async def shutdown_db() -> None:
            async with cls.engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            await cls.engine.dispose()

        asyncio.run(shutdown_db())

    def _seed_uploaded_file(self, *, filename: str, storage_key: str) -> str:
        file_id = str(uuid4())
        room_id = str(uuid4())
        user_id = str(uuid4())

        async def insert_rows() -> None:
            async with self.session_factory() as session:
                session.add(User(id=user_id, email=f"{user_id}@example.com"))
                session.add(
                    Room(
                        id=room_id,
                        owner_user_id=user_id,
                        name="File Parse Room",
                        goal=None,
                        current_mode="orchestrator",
                        pending_mode=None,
                    )
                )
                session.add(
                    UploadedFile(
                        id=file_id,
                        user_id=user_id,
                        room_id=room_id,
                        filename=filename,
                        storage_key=storage_key,
                        content_type="text/plain",
                        file_size=12,
                        parse_status="pending",
                    )
                )
                await session.commit()

        asyncio.run(insert_rows())
        return file_id

    def test_file_parse_marks_completed_for_supported_file(self) -> None:
        file_id = self._seed_uploaded_file(filename="notes.txt", storage_key="rooms/r1/f1/notes.txt")

        async def fake_downloader(_storage_key: str) -> bytes:
            return b"hello from txt"

        result = asyncio.run(
            file_parse(
                {
                    "session_factory": self.session_factory,
                    "storage_downloader": fake_downloader,
                },
                file_id,
            )
        )
        self.assertEqual(result["status"], "completed")

        async def fetch_row() -> UploadedFile | None:
            async with self.session_factory() as session:
                return await session.get(UploadedFile, file_id)

        row = asyncio.run(fetch_row())
        self.assertIsNotNone(row)
        self.assertEqual(row.parse_status, "completed")
        self.assertEqual(row.parsed_text, "hello from txt")
        self.assertIsNone(row.error_message)

    def test_file_parse_marks_failed_for_unsupported_format(self) -> None:
        file_id = self._seed_uploaded_file(filename="report.pdf", storage_key="rooms/r1/f2/report.pdf")

        async def fake_downloader(_storage_key: str) -> bytes:
            return b"%PDF-1.4"

        result = asyncio.run(
            file_parse(
                {
                    "session_factory": self.session_factory,
                    "storage_downloader": fake_downloader,
                },
                file_id,
            )
        )
        self.assertEqual(result["status"], "failed")
        self.assertIn("Unsupported file format", result["error"])

        async def fetch_row() -> UploadedFile | None:
            async with self.session_factory() as session:
                return await session.get(UploadedFile, file_id)

        row = asyncio.run(fetch_row())
        self.assertIsNotNone(row)
        self.assertEqual(row.parse_status, "failed")
        self.assertIsNone(row.parsed_text)
        self.assertIn("Unsupported file format", row.error_message or "")

    def test_file_parse_marks_failed_when_download_errors(self) -> None:
        file_id = self._seed_uploaded_file(filename="data.csv", storage_key="rooms/r1/f3/data.csv")

        async def failing_downloader(_storage_key: str) -> bytes:
            raise RuntimeError("download failed")

        result = asyncio.run(
            file_parse(
                {
                    "session_factory": self.session_factory,
                    "storage_downloader": failing_downloader,
                },
                file_id,
            )
        )
        self.assertEqual(result["status"], "failed")
        self.assertIn("download failed", result["error"])

        async def fetch_row() -> UploadedFile | None:
            async with self.session_factory() as session:
                return await session.get(UploadedFile, file_id)

        row = asyncio.run(fetch_row())
        self.assertIsNotNone(row)
        self.assertEqual(row.parse_status, "failed")
        self.assertIsNone(row.parsed_text)
        self.assertIn("download failed", row.error_message or "")

    def test_file_parse_returns_not_found_when_file_row_missing(self) -> None:
        missing_file_id = str(uuid4())
        downloader_called = False

        async def fake_downloader(_storage_key: str) -> bytes:
            nonlocal downloader_called
            downloader_called = True
            return b"unused"

        result = asyncio.run(
            file_parse(
                {
                    "session_factory": self.session_factory,
                    "storage_downloader": fake_downloader,
                },
                missing_file_id,
            )
        )
        self.assertEqual(result, {"status": "not_found", "file_id": missing_file_id})
        self.assertFalse(downloader_called)

    def test_file_parse_marks_completed_for_csv_and_normalizes_rows(self) -> None:
        file_id = self._seed_uploaded_file(filename="scores.csv", storage_key="rooms/r1/f4/scores.csv")

        async def fake_downloader(_storage_key: str) -> bytes:
            return b"name,score\nalice,10\nbob,8\n"

        result = asyncio.run(
            file_parse(
                {
                    "session_factory": self.session_factory,
                    "storage_downloader": fake_downloader,
                },
                file_id,
            )
        )
        self.assertEqual(result["status"], "completed")

        async def fetch_row() -> UploadedFile | None:
            async with self.session_factory() as session:
                return await session.get(UploadedFile, file_id)

        row = asyncio.run(fetch_row())
        self.assertIsNotNone(row)
        self.assertEqual(row.parse_status, "completed")
        self.assertEqual(row.parsed_text, "name | score\nalice | 10\nbob | 8")
        self.assertIsNone(row.error_message)


if __name__ == "__main__":
    unittest.main()
