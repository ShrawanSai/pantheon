from __future__ import annotations

import logging
from dataclasses import dataclass

from pydantic import BaseModel

from apps.api.app.services.llm.gateway import GatewayMessage, GatewayRequest, LlmGateway


_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class SummaryGenerationResult:
    summary_text: str
    used_fallback: bool


class _GenerationResponse(BaseModel):
    summary_text: str


async def generate_summary_text(
    raw_summary_text: str,
    gateway: LlmGateway,
    model_alias: str,
) -> SummaryGenerationResult:
    prompt = (
        "Rewrite the provided session summary into a concise, high-signal executive summary.\n"
        "Keep facts and decisions accurate, avoid speculation, and keep it under 220 words.\n\n"
        f"Input summary:\n{raw_summary_text}\n\n"
        "Respond ONLY with valid JSON in exactly this format:\n"
        "{\n"
        '  "summary_text": "..." \n'
        "}\n\n"
        "Do not include any other text, explanation, or markdown."
    )
    response = await gateway.generate(
        GatewayRequest(
            model_alias=model_alias,
            messages=[GatewayMessage(role="system", content=prompt)],
            max_output_tokens=512,
        )
    )

    fallback_text = raw_summary_text.strip()[:1200]
    try:
        parsed = _GenerationResponse.model_validate_json(response.text)
        summary_text = parsed.summary_text.strip()
        if not summary_text:
            raise ValueError("summary_text is blank")
        return SummaryGenerationResult(summary_text=summary_text, used_fallback=False)
    except Exception as exc:
        _LOGGER.warning(
            "Summary generator failed to parse response JSON; using deterministic fallback summary. error=%s",
            exc,
        )
        return SummaryGenerationResult(summary_text=fallback_text, used_fallback=True)
