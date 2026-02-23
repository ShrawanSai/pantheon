from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AgentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    model_alias: str = Field(min_length=1, max_length=64)
    role_prompt: str = Field(default="")
    tool_permissions: list[str] = Field(default_factory=list)

    @field_validator("agent_key", "name", "model_alias")
    @classmethod
    def _strip_required_non_blank(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("must not be blank.")
        return trimmed

    @field_validator("role_prompt")
    @classmethod
    def _strip_role_prompt(cls, value: str) -> str:
        return value.strip()


class AgentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_key: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    model_alias: str | None = Field(default=None, min_length=1, max_length=64)
    role_prompt: str | None = Field(default=None)
    tool_permissions: list[str] | None = Field(default=None)

    @field_validator("agent_key", "name", "model_alias")
    @classmethod
    def _strip_optional_non_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if trimmed == "":
            raise ValueError("must not be blank.")
        return trimmed

    @field_validator("role_prompt")
    @classmethod
    def _strip_optional_role_prompt(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()


class AgentRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    owner_user_id: str
    agent_key: str
    name: str
    model_alias: str
    role_prompt: str
    tool_permissions: list[str]
    created_at: datetime
    updated_at: datetime


class AgentListRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agents: list[AgentRead]
    total: int
