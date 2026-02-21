from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class UsageRecord:
    user_id: str
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


class UsageRecorder:
    async def record_llm_usage(self, record: UsageRecord) -> None:
        # MVP hook stub: persistence integration lands in billing/usage sprint.
        _ = record


_usage_recorder = UsageRecorder()


def get_usage_recorder() -> UsageRecorder:
    return _usage_recorder

