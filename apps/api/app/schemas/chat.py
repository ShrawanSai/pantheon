from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

TurnMode = Literal["manual", "tag", "roundtable", "orchestrator"]


class SessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SessionRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    room_id: str
    started_by_user_id: str
    created_at: datetime
    deleted_at: datetime | None


class TurnCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1)
    model_alias_override: str | None = Field(default=None, max_length=64)

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("message must not be blank.")
        return trimmed

    @field_validator("model_alias_override")
    @classmethod
    def validate_alias(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None


class TurnRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    session_id: str
    turn_index: int
    mode: TurnMode
    user_input: str
    assistant_output: str
    status: str
    model_alias_used: str
    summary_triggered: bool
    prune_triggered: bool
    overflow_rejected: bool
    balance_after: str | None = None
    low_balance: bool = False
    summary_used_fallback: bool = False
    created_at: datetime
