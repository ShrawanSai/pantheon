from __future__ import annotations

import logging
from dataclasses import dataclass

from pydantic import BaseModel, field_validator

from apps.api.app.services.llm.gateway import GatewayMessage, GatewayRequest, LlmGateway


_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class SummaryStructure:
    key_facts: list[str]
    decisions: list[str]
    open_questions: list[str]
    action_items: list[str]


class _ExtractionResponse(BaseModel):
    key_facts: list[str] = []
    decisions: list[str] = []
    open_questions: list[str] = []
    action_items: list[str] = []

    @field_validator("key_facts", "decisions", "open_questions", "action_items")
    @classmethod
    def _strip_and_filter_items(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]


async def extract_summary_structure(
    summary_text: str,
    gateway: LlmGateway,
    model_alias: str,
) -> SummaryStructure:
    prompt = (
        "Given the following session summary, extract structured information.\n\n"
        f"Summary:\n{summary_text}\n\n"
        "Respond ONLY with valid JSON in exactly this format:\n"
        "{\n"
        '  "key_facts": ["..."],\n'
        '  "decisions": ["..."],\n'
        '  "open_questions": ["..."],\n'
        '  "action_items": ["..."]\n'
        "}\n\n"
        "All values must be JSON arrays of strings. Use [] if none apply.\n"
        "Do not include any other text, explanation, or markdown."
    )
    response = await gateway.generate(
        GatewayRequest(
            model_alias=model_alias,
            messages=[GatewayMessage(role="system", content=prompt)],
            max_output_tokens=512,
        )
    )

    try:
        parsed = _ExtractionResponse.model_validate_json(response.text)
        return SummaryStructure(
            key_facts=parsed.key_facts,
            decisions=parsed.decisions,
            open_questions=parsed.open_questions,
            action_items=parsed.action_items,
        )
    except Exception as exc:
        _LOGGER.warning("Summary extractor failed to parse response JSON; returning empty structure. error=%s", exc)
        return SummaryStructure(
            key_facts=[],
            decisions=[],
            open_questions=[],
            action_items=[],
        )
