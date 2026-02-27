from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.db.models import UploadedFile

TOOL_NAME = "file_read"


@dataclass(frozen=True)
class FileReadResult:
    status: Literal["completed", "pending", "failed", "not_found"]
    content: str | None
    error: str | None


class FileReadTool(Protocol):
    async def read(self, *, file_id: str, db: AsyncSession, room_id: str | None = None, session_id: str | None = None) -> FileReadResult: ...


class DefaultFileReadTool:
    async def read(self, *, file_id: str, db: AsyncSession, room_id: str | None = None, session_id: str | None = None) -> FileReadResult:
        row = await db.get(UploadedFile, file_id)
        if row is None:
            return FileReadResult(status="not_found", content=None, error="File not found.")

        # Tell type checker row is not None
        assert row is not None

        if room_id and row.room_id != room_id:
            return FileReadResult(status="not_found", content=None, error="File not found.")
        if session_id and row.session_id != session_id:
            return FileReadResult(status="not_found", content=None, error="File not found.")

        if row.parse_status == "pending":
            return FileReadResult(
                status="pending",
                content=None,
                error="File is still being processed.",
            )
        if row.parse_status == "failed":
            return FileReadResult(
                status="failed",
                content=None,
                error=row.error_message or "File parse failed.",
            )
        if row.parse_status == "completed":
            return FileReadResult(
                status="completed",
                content=row.parsed_text,
                error=None,
            )

        return FileReadResult(status="failed", content=None, error="File parse status is invalid.")


_file_read_tool: FileReadTool = DefaultFileReadTool()


def get_file_read_tool() -> FileReadTool:
    return _file_read_tool
