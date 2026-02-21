from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

RoomMode = Literal["manual", "tag", "roundtable", "orchestrator"]


class RoomCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    goal: str | None = Field(default=None)
    current_mode: RoomMode = "orchestrator"

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("name must not be blank.")
        return trimmed


class RoomRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    owner_user_id: str
    name: str
    goal: str | None
    current_mode: RoomMode
    pending_mode: RoomMode | None
    created_at: datetime
    updated_at: datetime


class RoomAgentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    model_alias: str = Field(min_length=1, max_length=64)
    role_prompt: str = Field(min_length=1)
    tool_permissions: list[str] = Field(default_factory=list)
    position: int | None = Field(default=None, ge=1)

    @field_validator("agent_key", "name", "model_alias", "role_prompt")
    @classmethod
    def validate_non_blank_string(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("must not be blank.")
        return trimmed


class RoomAgentRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    room_id: str
    agent_key: str
    name: str
    model_alias: str
    role_prompt: str
    tool_permissions: list[str]
    position: int
    created_at: datetime
