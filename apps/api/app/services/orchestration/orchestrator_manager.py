from __future__ import annotations

import logging
from dataclasses import dataclass

from pydantic import BaseModel

from apps.api.app.db.models import Agent
from apps.api.app.services.llm.gateway import GatewayMessage, GatewayRequest, GatewayResponse, LlmGateway


_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class OrchestratorRoutingDecision:
    selected_agent_keys: tuple[str, ...]

    @property
    def selected_agent_key(self) -> str:
        return self.selected_agent_keys[0]


class _RoutingResponse(BaseModel):
    selected_agent_keys: list[str] = []
    selected_agent_key: str | None = None


@dataclass(frozen=True)
class OrchestratorSynthesisResult:
    text: str
    response: GatewayResponse


def _build_manager_system_prompt(agents: list[Agent]) -> str:
    lines = [
        "You are a routing manager for a multi-agent council room.",
        "",
        "Available agents:",
    ]
    for agent in agents:
        lines.append(f'- key: "{agent.agent_key}", role: "{agent.role_prompt[:120]}"')
    lines.extend(
        [
            "",
            "Select up to 3 best agents to handle the user's request in execution order.",
            "",
            "Respond ONLY with valid JSON in exactly this format:",
            '{"selected_agent_keys": ["<key1>", "<key2>"]}',
            "",
            "Do not include any other text, explanation, or markdown.",
        ]
    )
    return "\n".join(lines)


def build_orchestrator_synthesis_messages(
    *,
    user_input: str,
    specialist_outputs: list[tuple[str, str]],
) -> list[GatewayMessage]:
    specialist_block = "\n\n".join(f"[{name}]: {text}" for name, text in specialist_outputs)
    return [
        GatewayMessage(
            role="system",
            content=(
                "You are the orchestrating manager agent. Specialists have responded to the user's request below. "
                "Synthesize their outputs into a single clear, consolidated response for the user. "
                "Do not add new information; integrate and summarize what the specialists provided."
            ),
        ),
        GatewayMessage(role="user", content=user_input),
        GatewayMessage(role="system", content=f"Specialist outputs:\n{specialist_block}"),
        GatewayMessage(role="system", content="Provide a concise synthesis of the above specialist perspectives."),
    ]


async def generate_orchestrator_synthesis(
    *,
    gateway: LlmGateway,
    manager_model_alias: str,
    user_input: str,
    specialist_outputs: list[tuple[str, str]],
    max_output_tokens: int,
) -> OrchestratorSynthesisResult | None:
    if not specialist_outputs:
        return None

    response = await gateway.generate(
        GatewayRequest(
            model_alias=manager_model_alias,
            messages=build_orchestrator_synthesis_messages(
                user_input=user_input,
                specialist_outputs=specialist_outputs,
            ),
            max_output_tokens=max_output_tokens,
        )
    )
    return OrchestratorSynthesisResult(text=response.text, response=response)


async def route_turn(
    agents: list[Agent],
    user_input: str,
    gateway: LlmGateway,
    manager_model_alias: str,
) -> OrchestratorRoutingDecision:
    if not agents:
        raise ValueError("route_turn requires at least one available agent.")

    fallback = OrchestratorRoutingDecision(selected_agent_keys=(agents[0].agent_key,))
    response = await gateway.generate(
        GatewayRequest(
            model_alias=manager_model_alias,
            messages=[
                GatewayMessage(role="system", content=_build_manager_system_prompt(agents)),
                GatewayMessage(role="user", content=user_input),
            ],
            max_output_tokens=256,
        )
    )

    try:
        parsed = _RoutingResponse.model_validate_json(response.text)
        selected_agent_keys = parsed.selected_agent_keys or (
            [parsed.selected_agent_key] if parsed.selected_agent_key else []
        )
        if not selected_agent_keys:
            raise ValueError("manager response contains no agent keys")

        normalized_keys: list[str] = []
        seen: set[str] = set()
        for key in selected_agent_keys:
            cleaned = str(key).strip()
            if not cleaned:
                continue
            lowered = cleaned.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            normalized_keys.append(cleaned)
            if len(normalized_keys) >= 3:
                break
    except Exception as exc:
        _LOGGER.warning(
            "Orchestrator manager returned invalid routing JSON; falling back to first agent. response=%r error=%s",
            response.text,
            exc,
        )
        return fallback

    by_key = {agent.agent_key.lower(): agent for agent in agents}
    selected: list[str] = []
    for key in normalized_keys:
        mapped = by_key.get(key.lower())
        if mapped is not None:
            selected.append(mapped.agent_key)

    if not selected:
        _LOGGER.warning(
            "Orchestrator manager selected no valid agent keys (%s); falling back to first agent.",
            normalized_keys,
        )
        return fallback

    return OrchestratorRoutingDecision(selected_agent_keys=tuple(selected))
