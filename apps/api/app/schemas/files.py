from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


ParseStatus = Literal["pending", "completed", "failed"]


class UploadedFileRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    user_id: str
    room_id: str | None = None
    session_id: str | None = None
    filename: str
    storage_key: str
    content_type: str
    file_size: int
    parse_status: ParseStatus
    parsed_text: str | None
    error_message: str | None
    created_at: datetime

