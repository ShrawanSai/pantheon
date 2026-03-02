from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

TurnMode = Literal["manual", "tag", "roundtable", "orchestrator"]
SessionMode = Literal["manual", "tag", "roundtable", "orchestrator", "standalone"]


class SessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SessionRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    room_id: str | None
    agent_id: str | None = None
    started_by_user_id: str
    name: str | None = None
    created_at: datetime
    deleted_at: datetime | None


class SessionUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)


class TurnCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1)
    model_alias_override: str | None = Field(default=None, max_length=64)
    tagged_agent_keys: list[str] | None = Field(default=None, max_length=32)

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

    @field_validator("tagged_agent_keys")
    @classmethod
    def validate_tagged_agent_keys(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in value:
            normalized = (raw or "").strip().lower()
            if not normalized:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            cleaned.append(normalized)
        return cleaned or None


class TurnRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    session_id: str
    turn_index: int
    mode: SessionMode
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


class SessionMessageRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    role: str
    agent_name: str | None
    content: str
    turn_id: str | None
    created_at: datetime


class SessionMessageListRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[SessionMessageRead]
    total: int


class SessionTurnHistoryRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    turn_index: int
    mode: SessionMode
    user_input: str
    assistant_output: str
    status: str
    created_at: datetime


class SessionTurnListRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turns: list[SessionTurnHistoryRead]
    total: int


# ── Session Analytics ─────────────────────────────────────────────────────────

class TurnCostRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn_id: str | None
    turn_index: int | None
    user_input_preview: str | None
    credits_burned: str
    total_tokens: int
    llm_call_count: int


class ModelCostRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_alias: str
    credits_burned: str
    input_tokens_fresh: int
    input_tokens_cached: int
    output_tokens: int
    total_tokens: int
    llm_call_count: int


class SessionAnalyticsRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    total_credits_burned: str
    total_input_tokens_fresh: int
    total_input_tokens_cached: int
    total_output_tokens: int
    total_tokens: int
    llm_call_count: int
    highest_cost_turn: TurnCostRead | None
    by_model: list[ModelCostRead]
    by_turn: list[TurnCostRead]
