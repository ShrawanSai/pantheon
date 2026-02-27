from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from pydantic import BaseModel, Field
from typing import Protocol

from apps.api.app.services.llm.gateway import GatewayMessage, GatewayRequest, LlmGateway

class RoutableAgent(Protocol):
    @property
    def agent_key(self) -> str | None: ...
    @property
    def role_prompt(self) -> str: ...
    @property
    def tool_permissions(self) -> tuple[str, ...]: ...

_LOGGER = logging.getLogger(__name__)


def _strip_json_fences(text: str) -> str:
    """Strip markdown code fences that LLMs often wrap JSON in."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        return match.group(1)
    return text


@dataclass(frozen=True)
class OrchestratorRoutingDecision:
    selected_agent_keys: tuple[str, ...]
    assignments: dict[str, str] = field(default_factory=dict) # key -> instruction

    @property
    def selected_agent_key(self) -> str:
        return self.selected_agent_keys[0] if self.selected_agent_keys else ""


class AgentAssignment(BaseModel):
    agent_key: str
    instruction: str


class _RoutingResponse(BaseModel):
    assignments: list[AgentAssignment] = []
    selected_agent_keys: list[str] = []
    selected_agent_key: str | None = None


class _RoundEvaluationResponse(BaseModel):
    should_continue: bool = Field(validation_alias="continue")


@dataclass(frozen=True)
class OrchestratorSynthesisResult:
    text: str
    response: GatewayResponse


@dataclass(frozen=True)
class OrchestratorRoundDecision:
    should_continue: bool


def _build_manager_system_prompt(
    agents: list[RoutableAgent],
    prior_round_outputs: list[tuple[str, str]] | None = None,
) -> str:
    lines = [
        "You are a routing manager for a multi-agent council room.",
        "Your job is to select the best agents from the room to answer the user's latest input.",
        "",
        "Available agents and their capabilities:",
    ]
    for agent in agents:
        tools = ", ".join(agent.tool_permissions) if agent.tool_permissions else "None"
        lines.append(f'- key: "{agent.agent_key}"\n  role: "{agent.role_prompt}"\n  tools: [{tools}]')
    if prior_round_outputs:
        lines.extend(
            [
                "",
                "Prior round specialist outputs (already covered - route for what is still missing):",
            ]
        )
        lines.extend(f"[{name}]: {text}" for name, text in prior_round_outputs)
    lines.extend(
        [
            "",
            "ROUTING RULES:",
            "1. Select up to 3 best agents to handle the user's request. For each agent, provide a specific, detailed instruction on what they should contribute.",
            "2. If the user asks for multiple perspectives, or if the task inherently applies to multiple agents, you MUST select ALL relevant agents at once in this single round.",
            "3. DO NOT select an agent that has already provided an output in prior rounds unless they explicitly need to respond to what another agent just said.",
            "4. Prefer running agents concurrently (selecting multiple keys at once) rather than sequencing them across multiple rounds, unless they depend on each other's output.",
            "",
            "Respond ONLY with valid JSON in exactly this format:",
            '{',
            '  "assignments": [',
            '    {"agent_key": "<key1>", "instruction": "Provide a technical overview of..."},',
            '    {"agent_key": "<key2>", "instruction": "Analyze the security implications of..."}',
            '  ]',
            '}',
            "",
            "CRITICAL: `assignments` MUST be a JSON array of objects with `agent_key` and `instruction`.",
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
    agents: list[RoutableAgent],
    user_input: str,
    gateway: LlmGateway,
    manager_model_alias: str,
    prior_round_outputs: list[tuple[str, str]] | None = None,
) -> OrchestratorRoutingDecision:
    if not agents:
        raise ValueError("route_turn requires at least one available agent.")

    fallback = OrchestratorRoutingDecision(selected_agent_keys=(agents[0].agent_key,))
    
    with open("orchestrator_debug.txt", "a", encoding="utf-8") as f:
        f.write(f"--- route_turn called ---\n")
        f.write(f"NUM AGENTS: {len(agents)}\n")
        f.write(f"AGENT KEYS: {[a.agent_key for a in agents]}\n")
        f.write(f"USER INPUT: {user_input[:100]}\n")
        f.write(f"PRIOR OUTPUTS: {'YES' if prior_round_outputs else 'NO'}\n")
    
    # Deterministic routing for explicit "all" requests on the first round
    user_lower = user_input.lower()
    if not prior_round_outputs and ("all " in user_lower) and len(agents) > 1:
        # If the user is asking for all agents/CEOs, just return them all. 
        # LLMs often struggle to output multiple JSON array elements even when instructed.
        keys = tuple(a.agent_key for a in agents if a.agent_key is not None)
        with open("orchestrator_debug.txt", "a", encoding="utf-8") as f:
            f.write(f"DETERMINISTIC ROUTING TRIGGERED! Keys: {keys}\n")
        if keys:
            return OrchestratorRoutingDecision(selected_agent_keys=keys)

    response = await gateway.generate(
        GatewayRequest(
            model_alias=manager_model_alias,
            messages=[
                GatewayMessage(
                    role="system",
                    content=_build_manager_system_prompt(agents, prior_round_outputs=prior_round_outputs),
                ),
                GatewayMessage(
                    role="user", 
                    content=f"User Request: {user_input}\n\nCRITICAL: If the user asks for multiple perspectives, return an array containing ALL relevant agent keys. Do not just return one."
                ),
            ],
            max_output_tokens=256,
        )
    )

    try:
        with open("orchestrator_debug.txt", "a", encoding="utf-8") as f:
            f.write(f"RAW LLM RESPONSE: {response.text}\n")
            
        parsed = _RoutingResponse.model_validate_json(_strip_json_fences(response.text))
        
        assignments_dict: dict[str, str] = {
            a.agent_key.strip().lower(): a.instruction 
            for a in parsed.assignments 
            if a.agent_key
        }

        selected_agent_keys = (
            [a.agent_key for a in parsed.assignments] 
            if parsed.assignments 
            else (parsed.selected_agent_keys or ([parsed.selected_agent_key] if parsed.selected_agent_key else []))
        )

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
    final_assignments: dict[str, str] = {}
    
    for key in normalized_keys:
        mapped = by_key.get(key.lower())
        if mapped is not None:
            active_key = mapped.agent_key
            selected.append(active_key)
            # Carry over the instruction if we have it
            instr = assignments_dict.get(key.lower(), "Please respond to the user's request.")
            final_assignments[active_key] = instr

    if not selected:
        if not prior_round_outputs:
            _LOGGER.warning(
                "Orchestrator manager selected no valid agent keys (%s) on first round; falling back to first agent.",
                normalized_keys,
            )
            return fallback
        else:
            # On subsequent rounds, empty selection is valid and means stop
            return OrchestratorRoutingDecision(selected_agent_keys=(), assignments={})

    return OrchestratorRoutingDecision(
        selected_agent_keys=tuple(selected),
        assignments=final_assignments
    )


async def evaluate_orchestrator_round(
    *,
    gateway: LlmGateway,
    manager_model_alias: str,
    user_input: str,
    all_round_outputs: list[tuple[str, str]],
    current_round: int,
    max_output_tokens: int = 128,
) -> OrchestratorRoundDecision:
    specialist_block = "\n\n".join(f"[{name}]: {text}" for name, text in all_round_outputs)
    response = await gateway.generate(
        GatewayRequest(
            model_alias=manager_model_alias,
            messages=[
                GatewayMessage(
                    role="system",
                    content=(
                        "You are the orchestrating manager agent. You have seen the user's request and all "
                        "specialist outputs collected so far. Decide if another specialist round is needed."
                    ),
                ),
                GatewayMessage(role="user", content=user_input),
                GatewayMessage(role="system", content=f"Specialist outputs so far:\n{specialist_block}"),
                GatewayMessage(
                    role="system",
                    content=(
                        f"Round {current_round} complete. Should another round of specialist consultation run to "
                        'better answer the user? Reply ONLY with valid JSON: {"continue": true} or {"continue": false}'
                    ),
                ),
            ],
            max_output_tokens=max_output_tokens,
        )
    )
    try:
        parsed_json = _RoundEvaluationResponse.model_validate_json(_strip_json_fences(response.text))
        return OrchestratorRoundDecision(should_continue=bool(parsed_json.should_continue))
    except Exception as exc:
        _LOGGER.warning(
            "Orchestrator manager returned invalid round evaluation JSON; ending loop. response=%r error=%s",
            response.text,
            exc,
        )
        return OrchestratorRoundDecision(should_continue=False)
