from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from apps.api.app.schemas.agents import AgentRead

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


class RoomModeUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str = Field(min_length=1, max_length=32)

    @field_validator("mode")
    @classmethod
    def validate_mode_non_blank(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("mode must not be blank.")
        return trimmed


class RoomAgentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(min_length=1, max_length=64)
    position: int | None = Field(default=None, ge=1)

    @field_validator("agent_id")
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
    agent_id: str
    agent: AgentRead
    position: int
    created_at: datetime
