from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.core.config import get_settings
from apps.api.app.db.models import LlmCallEvent


@dataclass(frozen=True)
class UsageRecord:
    user_id: str
    room_id: str | None
    session_id: str
    turn_id: str
    model_alias: str
    provider_model: str
    input_tokens_fresh: int
    input_tokens_cached: int
    output_tokens: int
    total_tokens: int
    oe_tokens_computed: float
    credits_burned: float
    recorded_at: datetime
    provider: str = "openrouter"
    provider_cost_usd: float = 0.0
    latency_ms: int | None = None
    status: str = "success"
    step_id: str | None = None
    agent_id: str | None = None
    request_id: str | None = None


class UsageRecorder:
    async def record_llm_usage(self, db: AsyncSession, record: UsageRecord) -> None:
        settings = get_settings()
        event = LlmCallEvent(
            id=str(uuid4()),
            user_id=record.user_id,
            room_id=record.room_id,
            direct_session_id=None,
            session_id=record.session_id,
            turn_id=record.turn_id,
            step_id=record.step_id,
            agent_id=record.agent_id,
            provider=record.provider,
            model_alias=record.model_alias,
            provider_model=record.provider_model,
            input_tokens_fresh=record.input_tokens_fresh,
            input_tokens_cached=record.input_tokens_cached,
            output_tokens=record.output_tokens,
            total_tokens=record.total_tokens,
            oe_tokens_computed=Decimal(str(record.oe_tokens_computed)),
            provider_cost_usd=Decimal(str(record.provider_cost_usd)),
            credits_burned=Decimal(str(record.credits_burned)),
            latency_ms=record.latency_ms,
            status=record.status,
            pricing_version=settings.pricing_version,
            request_id=record.request_id,
            created_at=record.recorded_at,
        )
        db.add(event)
        await db.commit()


_usage_recorder = UsageRecorder()


def get_usage_recorder() -> UsageRecorder:
    return _usage_recorder
