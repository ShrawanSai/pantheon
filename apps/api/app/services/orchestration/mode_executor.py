from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.services.llm.gateway import (
    GatewayMessage,
    GatewayRequest,
    GatewayUsage,
    LlmGateway,
    get_llm_gateway,
)
from apps.api.app.services.tools.file_tool import FileReadTool, get_file_read_tool
from apps.api.app.services.tools.search_tool import SearchTool, get_search_tool
from apps.api.app.services.tools.mode_tools import (
    make_web_search_tool_execute,
    make_read_file_tool_execute,
    ToolInvocationTelemetry,
)
from apps.api.app.services.llm.structured_response import AgentResponse
from apps.api.app.services.orchestration.context_manager import build_tool_memory_block
from apps.api.app.services.orchestration.orchestrator_manager import (
    route_turn,
    generate_orchestrator_synthesis,
    evaluate_orchestrator_round,
    build_orchestrator_synthesis_messages,
)

_LOGGER = logging.getLogger(__name__)

RoomMode = Literal["manual", "tag", "roundtable", "orchestrator", "standalone"]

EventSink = Callable[[str, dict], Awaitable[None]]

@dataclass
class ActiveAgent:
    agent_id: str | None
    agent_key: str | None
    name: str
    model_alias: str
    role_prompt: str
    tool_permissions: tuple[str, ...]

@dataclass
class TurnExecutionState:
    session_id: str
    turn_index: int
    user_input: str
    room_mode: RoomMode
    active_agents: list[ActiveAgent]
    primary_context_messages: list[GatewayMessage]
    max_output_tokens: int
    room_id: str | None = None

    # Per-agent recent ToolCallEvent rows, keyed by agent_key
    agent_tool_events: dict[str, list[Any]] = field(default_factory=dict)

    current_round: int = 1
    total_invocations: int = 0
    specialist_outputs: list[tuple[str, str]] = field(default_factory=list)
    current_status: Literal["running", "partial", "completed", "failed"] = "running"
    
    final_synthesis: str | None = None
    
    # Tracking
    usage_entries: list[tuple[str | None, str, str, int, int, int, int]] = field(default_factory=list)
    tool_trace_entries: list[tuple[ActiveAgent, tuple[ToolCallRecord, ...]]] = field(default_factory=list)
    assistant_entries: list[tuple[ActiveAgent, str]] = field(default_factory=list)
    per_round_entries: list[list[tuple[ActiveAgent, str]]] = field(default_factory=list)

@dataclass(frozen=True)
class ToolCallRecord:
    tool_name: str
    input_json: str
    output_json: str
    status: str
    latency_ms: int | None
    tool_call_id: str | None = None


class TurnExecutor(Protocol):
    async def run_turn(
        self, 
        db: AsyncSession, 
        state: TurnExecutionState,
        event_sink: EventSink | None = None
    ) -> TurnExecutionState: ...


class PurePythonModeExecutor:
    def __init__(
        self,
        llm_gateway: LlmGateway,
        search_tool: SearchTool | None = None,
        file_read_tool: FileReadTool | None = None,
    ) -> None:
        self._llm_gateway = llm_gateway
        self._search_tool = search_tool or get_search_tool()
        self._file_read_tool = file_read_tool or get_file_read_tool()

    def _assemble_agent_messages(
        self,
        state: TurnExecutionState,
        agent: ActiveAgent,
        *,
        mode_instruction: str,
        prior_agent_outputs: list[GatewayMessage] | None = None,
    ) -> list[GatewayMessage]:
        """Build the full message stack for an agent invocation.

        Layer order:
        1. Identity (agent name + role prompt)
        2. Mode-specific behavioral contract
        3. Room/session context + summary + history (from primary_context_messages)
        4. Tool memory (prior tool calls for this agent)
        5. Prior agent outputs (roundtable shared history / orchestrator specialist outputs)
        """
        messages: list[GatewayMessage] = []

        # Layer 1: Identity
        messages.append(GatewayMessage(
            role="system",
            content=f"You are {agent.name}. {agent.role_prompt}",
        ))

        # Layer 2: Behavioral contract (mode-specific rules)
        messages.append(GatewayMessage(role="system", content=mode_instruction))

        # Layer 3: Primary context (room/session context, summary, history, current turn)
        messages.extend(state.primary_context_messages)

        # Layer 4: Tool memory
        tool_events = state.agent_tool_events.get(agent.agent_key or "", [])
        tool_block = build_tool_memory_block(tool_events)
        if tool_block:
            messages.append(GatewayMessage(role="system", content=tool_block))

        # Layer 5: Prior agent outputs (roundtable / orchestrator)
        if prior_agent_outputs:
            messages.extend(prior_agent_outputs)

        return messages

    def _build_single_speaker_stop_sequences(
        self,
        *,
        current_speaker: str,
        other_speakers: list[str],
        include_manager: bool,
        max_sequences: int = 4,
    ) -> list[str]:
        candidates: list[str] = []
        if include_manager:
            candidates.extend(["\nManager:", "Manager:"])

        for name in other_speakers:
            if name.lower() == current_speaker.lower():
                continue
            candidates.extend([f"\n{name}:", f"{name}:", f"\n{name.title()}:", f"{name.title()}:"])

        seen: set[str] = set()
        output: list[str] = []
        for item in candidates:
            if item in seen:
                continue
            seen.add(item)
            output.append(item)
            if len(output) >= max_sequences:
                break
        return output

    def _sanitize_single_speaker_output(
        self,
        *,
        text: str,
        current_speaker: str,
        disallowed_speakers: list[str],
        include_manager: bool,
    ) -> str:
        if not text:
            return text

        own_prefix = re.compile(
            rf"^\s*(?:\[{re.escape(current_speaker)}\]|{re.escape(current_speaker)})\s*:\s*",
            flags=re.IGNORECASE,
        )
        manager_prefix = re.compile(r"^\s*(?:\[manager\]|manager)\s*:\s*", flags=re.IGNORECASE)

        disallowed = {name.strip().lower() for name in disallowed_speakers if name and name.strip()}
        disallowed.discard(current_speaker.strip().lower())

        cleaned_lines: list[str] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                if cleaned_lines:
                    cleaned_lines.append("")
                continue
            if line == "---" or line.lower().startswith("manager synthesis"):
                break

            line = own_prefix.sub("", line)
            if include_manager:
                line = manager_prefix.sub("", line)
            lower_line = line.lower()

            if include_manager and (
                lower_line.startswith("manager:")
                or lower_line.startswith("[manager]")
                or lower_line.startswith("manager says:")
            ):
                if cleaned_lines:
                    break
                continue

            if any(
                lower_line.startswith(f"{name}:")
                or lower_line.startswith(f"[{name}]")
                or lower_line.startswith(f"{name} says:")
                for name in disallowed
            ):
                if cleaned_lines:
                    break
                continue

            cleaned_lines.append(line)

        return "\n".join(cleaned_lines).strip()

    async def _invoke_agent(
        self, 
        state: TurnExecutionState, 
        agent: ActiveAgent, 
        base_messages: list[GatewayMessage], 
        db: AsyncSession,
        event_sink: EventSink | None = None,
        stop_sequences: list[str] | None = None
    ) -> tuple[str, bool]:
        telemetry_records: list[ToolInvocationTelemetry] = []
        
        local_tools = {}
        if "search" in agent.tool_permissions and self._search_tool:
            local_tools["search"] = make_web_search_tool_execute(
                search_tool=self._search_tool,
                telemetry_sink=telemetry_records.append,
            )
        if "file_read" in agent.tool_permissions and self._file_read_tool:
            local_tools["file_read"] = make_read_file_tool_execute(
                room_id=state.room_id,
                session_id=state.session_id,
                db=db,
                file_tool=self._file_read_tool,
                telemetry_sink=telemetry_records.append,
            )
            
        messages = list(base_messages)
        loop_limit = 4
        
        try:
            for _ in range(loop_limit):
                req = GatewayRequest(
                    model_alias=agent.model_alias,
                    messages=messages,
                    max_output_tokens=state.max_output_tokens,
                    allowed_tools=agent.tool_permissions,
                    response_schema=AgentResponse,
                    stop_sequences=stop_sequences,
                )
                
                if event_sink:
                    _LOGGER.info("Sending agent_start for %s", agent.name)
                    await event_sink("agent_start", {"agent_name": agent.name, "agent_key": agent.agent_key})

                # If tools are permitted, just use generate to ensure tool_calls are cleanly extracted.
                # If streaming is requested and no tools, use stream mode.
                if agent.tool_permissions or not event_sink:
                    # Debug: Log the first message to verify separators
                    if messages:
                         _LOGGER.info("FINAL PAYLOAD FIRST MSG: %s", messages[0].content)
                         _LOGGER.info("FINAL PAYLOAD LAST MSG: %s", messages[-1].content)
                    
                    response = await self._llm_gateway.generate(req)
                    state.usage_entries.append((
                        agent.agent_id,
                        agent.model_alias,
                        response.provider_model,
                        response.usage.input_tokens_fresh,
                        response.usage.input_tokens_cached,
                        response.usage.output_tokens,
                        response.usage.total_tokens
                    ))

                    if not response.tool_calls:
                        tool_records = self._convert_telemetry(telemetry_records)
                        if tool_records:
                            state.tool_trace_entries.append((agent, tool_records))
                        if event_sink:
                            await event_sink("chunk", {"delta": response.text})
                            await event_sink("agent_end", {"agent_name": agent.name})
                        return response.text, True
                        
                    messages.append(GatewayMessage(role="assistant", content=response.text, tool_calls=response.tool_calls))
                    
                    for tc in response.tool_calls:
                        tc_id = tc["id"]
                        fn_name = tc["function"]["name"]
                        fn_args = tc["function"]["arguments"]
                        
                        try:
                            args_dict = json.loads(fn_args)
                        except json.JSONDecodeError:
                            args_dict = {}

                        if event_sink:
                            await event_sink("tool_start", {"tool": fn_name, "args": args_dict})

                        if fn_name in local_tools:
                            try:
                                result_str = await local_tools[fn_name](**args_dict)
                            except Exception as e:
                                result_str = f"Tool Error: {str(e)}"
                        else:
                            result_str = f"ToolError: Unknown tool {fn_name}"
                            
                        if event_sink:
                            await event_sink("tool_end", {"tool": fn_name, "result": result_str})

                        messages.append(GatewayMessage(role="tool", content=result_str, tool_call_id=tc_id))
                else:
                    # Native streaming chunk delivery (no tools)
                    stream_ctx = await self._llm_gateway.stream(req)
                    output_parts = []
                    is_first_chunk = True
                    async for delta in stream_ctx.chunks:
                        output_parts.append(delta)
                        await event_sink("chunk", {"delta": delta})
                            
                    if event_sink:
                        await event_sink("agent_end", {"agent_name": agent.name})
                            
                    text_out = "".join(output_parts)
                    usage_obj = await stream_ctx.usage_future
                    provider_model = await stream_ctx.provider_model_future

                    state.usage_entries.append((
                        agent.agent_id,
                        agent.model_alias,
                        provider_model,
                        usage_obj.input_tokens_fresh,
                        usage_obj.input_tokens_cached,
                        usage_obj.output_tokens,
                        usage_obj.total_tokens
                    ))
                    return text_out, True
                    
            text_out = "Agent iteration limit exceeded due to too many tool calls."
            return text_out, False
            
        except Exception as exc:
            _LOGGER.exception("Agent %s failed during invocation", agent.name)
            error_msg = f"[[agent_error]] type={exc.__class__.__name__} message={str(exc)}"
            if event_sink:
                await event_sink("chunk", {"delta": f"{agent.name}: {error_msg}"})
            return error_msg, False

    def _convert_telemetry(self, telemetry: list[ToolInvocationTelemetry]) -> tuple[ToolCallRecord, ...]:
        rows: list[ToolCallRecord] = []
        for index, row in enumerate(telemetry, start=1):
            rows.append(
                ToolCallRecord(
                    tool_name=row.tool_name,
                    input_json=row.input_json,
                    output_json=row.output_json,
                    status=row.status,
                    latency_ms=row.latency_ms,
                    tool_call_id=f"tool_call_{index}",
                )
            )
        return tuple(rows)

    async def run_turn(
        self, 
        db: AsyncSession, 
        state: TurnExecutionState,
        event_sink: EventSink | None = None
    ) -> TurnExecutionState:
        if state.room_mode in ("manual", "standalone", "tag"):
            await self._execute_manual(db, state, event_sink)
        elif state.room_mode == "roundtable":
            await self._execute_roundtable(db, state, event_sink)
        elif state.room_mode == "orchestrator":
            await self._execute_orchestrator(db, state, event_sink)
        return state

    async def _execute_manual(
        self,
        db: AsyncSession,
        state: TurnExecutionState,
        event_sink: EventSink | None = None
    ):
        agent = state.active_agents[0]
        base_messages = self._assemble_agent_messages(
            state, agent,
            mode_instruction="Respond directly to the user's message.",
        )
        text, success = await self._invoke_agent(state, agent, base_messages, db, event_sink)
        
        state.assistant_entries.append((agent, text))
        state.per_round_entries.append([(agent, text)])
        state.specialist_outputs.append((agent.name, text))
        if not success:
            state.current_status = "partial"

    async def _execute_roundtable(
        self, 
        db: AsyncSession, 
        state: TurnExecutionState,
        event_sink: EventSink | None = None
    ):
        user_input_lower = state.user_input.lower()
        
        # If the user explicitly mentors @agent_key, that agent should respond first
        def _sort_key(item: tuple[int, ActiveAgent]) -> tuple[int, int]:
            idx, agent = item
            mention_key = f"@{agent.agent_key.lower()}" if agent.agent_key else ""
            priority = 0 if mention_key and mention_key in user_input_lower else 1
            return (priority, idx)

        ordered_agents = [
            agent for _, agent in sorted(enumerate(state.active_agents), key=_sort_key)
        ]
        
        other_names_lower = [a.name.lower() for a in state.active_agents]

        shared_history: list[GatewayMessage] = []
        for agent in ordered_agents:
            other_names_str = ", ".join(n for n in other_names_lower if n != agent.name.lower())
            other_example = other_names_lower[0].title() if other_names_lower else "OtherAgent"
            mode_instruction = (
                f"Room mode: roundtable\n"
                f"You are participating in a group discussion. Respond ONLY as {agent.name}.\n"
                f"DO NOT include name tags like '[{agent.name}]:' or '{agent.name}:' in your response.\n"
                f"DO NOT write responses, dialogue, or script lines for any other agents ({other_names_str}).\n"
                f"When another agent is @mentioned (e.g., @{other_example}), answer ONLY on your behalf, then STOP.\n\n"
                f"BAD EXAMPLE (Roleplaying others):\n"
                f"[My thought about the topic.]\n\n"
                f"{other_example}: [Their thought about the topic.]\n\n"
                f"GOOD EXAMPLE (Answering only for myself):\n"
                f"[My thought about the topic.]"
            )
            base_messages = self._assemble_agent_messages(
                state, agent,
                mode_instruction=mode_instruction,
                prior_agent_outputs=shared_history if shared_history else None,
            )

            stop_seqs = self._build_single_speaker_stop_sequences(
                current_speaker=agent.name,
                other_speakers=[a.name for a in state.active_agents],
                include_manager=False,
            )
            stop_seqs.append("\n---")

            text, success = await self._invoke_agent(state, agent, base_messages, db, event_sink, stop_sequences=stop_seqs)

            if success and text:
                text = self._sanitize_single_speaker_output(
                    text=text,
                    current_speaker=agent.name,
                    disallowed_speakers=[a.name for a in state.active_agents],
                    include_manager=False,
                )

            state.assistant_entries.append((agent, text))
            state.specialist_outputs.append((agent.name, text))
            
            if success:
                # IMPORTANT: Use role="user" for other agents' speech. 
                # If we use "assistant", the LLM thinks *it* said this previously, 
                # which causes it to hallucinate or return an empty string.
                shared_history.append(GatewayMessage(role="user", content=f"[{agent.name} just said]:\n{text}"))
            else:
                state.current_status = "partial"
                
        state.per_round_entries.append(state.assistant_entries)

    async def _execute_orchestrator(
        self, 
        db: AsyncSession, 
        state: TurnExecutionState,
        event_sink: EventSink | None = None
    ):
        from apps.api.app.core.config import get_settings
        settings = get_settings()
        
        manager_alias = settings.orchestrator_manager_model_alias
        max_depth = max(settings.orchestrator_max_depth, 1)
        max_cap = max(settings.orchestrator_max_specialist_invocations, 1)
        
        while state.current_round <= max_depth and state.total_invocations < max_cap:
            if event_sink:
                await event_sink("round_start", {"round": state.current_round})

            prior_outputs = state.specialist_outputs if state.current_round > 1 else None
            
            routing = await route_turn(
                agents=state.active_agents, 
                user_input=state.user_input,
                gateway=self._llm_gateway,
                manager_model_alias=manager_alias,
                prior_round_outputs=prior_outputs,
            )
            
            by_key = {a.agent_key.lower(): a for a in state.active_agents if a.agent_key}
            round_assignments = [by_key[k.lower()] for k in routing.selected_agent_keys if k.lower() in by_key]
            if not round_assignments:
                if state.current_round == 1:
                    round_assignments = [state.active_agents[0]]
                else:
                    # If routing explicitly selects nobody after round 1, respect it and stop early
                    if event_sink:
                        await event_sink("manager_think", {
                            "phase": "evaluation",
                            "round": state.current_round,
                            "decision": "synthesize"
                        })
                    break
                    
            remaining = max_cap - state.total_invocations
            round_assignments = round_assignments[:min(3, remaining)]
            if not round_assignments:
                break
                
            round_outputs = []
            
            if event_sink:
                await event_sink("manager_think", {
                    "phase": "routing",
                    "round": state.current_round,
                    "target_agents": [a.name for a in round_assignments]
                })

            council_list = ", ".join(a.name for a in state.active_agents)
            for agent in round_assignments:
                # Get the instruction for this specific agent from the routing result
                instruction = routing.assignments.get(agent.agent_key, "Please provide your expertise on the user's request.")

                mode_instruction = (
                    f"You are in a meeting moderated by an Orchestrating Manager.\n"
                    f"The Council consists of: {council_list}.\n\n"
                    f"The Manager has specifically called upon YOU ({agent.name}) with these instructions:\n"
                    f"'{instruction}'\n\n"
                    f"RULES:\n"
                    f"1. Stay in character as {agent.name}.\n"
                    f"2. You are NOT the Manager. Do not moderate, summarize, or assign tasks.\n"
                    f"3. Respond ONLY with your own direct speech from your unique perspective.\n"
                    f"4. DO NOT include name tags like '[{agent.name}]:' or '{agent.name}:'."
                )

                prior_outputs: list[GatewayMessage] | None = None
                if state.specialist_outputs:
                    specialist_block = "\n\n".join(f"[{name} just said]:\n{text}" for name, text in state.specialist_outputs)
                    prior_outputs = [
                        GatewayMessage(role="user", content=f"Previous specialist outputs in this room:\n{specialist_block}")
                    ]

                base_messages = self._assemble_agent_messages(
                    state, agent,
                    mode_instruction=mode_instruction,
                    prior_agent_outputs=prior_outputs,
                )

                stop_seqs = self._build_single_speaker_stop_sequences(
                    current_speaker=agent.name,
                    other_speakers=[a.name for a in state.active_agents],
                    include_manager=True,
                )
                stop_seqs.append("\n---")

                text, success = await self._invoke_agent(
                    state,
                    agent,
                    base_messages,
                    db,
                    event_sink,
                    stop_sequences=stop_seqs,
                )
                if success and text:
                    cleaned_text = self._sanitize_single_speaker_output(
                        text=text,
                        current_speaker=agent.name,
                        disallowed_speakers=[a.name for a in state.active_agents],
                        include_manager=True,
                    )
                    if cleaned_text != text:
                        _LOGGER.warning(
                            "Sanitized orchestrator output for agent=%s (possible multi-speaker contamination).",
                            agent.name,
                        )
                    if not cleaned_text:
                        success = False
                        text = "[[agent_error]] type=SpeakerContamination message=agent_output_not_single_speaker"
                    else:
                        text = cleaned_text
                round_outputs.append((agent, text))
                if success:
                    state.specialist_outputs.append((agent.name, text))
                    state.assistant_entries.append((agent, text))
                state.total_invocations += 1
                
            state.per_round_entries.append(round_outputs)
            
            if event_sink:
                await event_sink("round_end", {"round": state.current_round})

            if not any(not text.startswith("[[agent_error]]") for _, text in round_outputs):
                break
                
            if state.current_round < max_depth and state.total_invocations < max_cap:
                eval_decision = await evaluate_orchestrator_round(
                    gateway=self._llm_gateway,
                    manager_model_alias=manager_alias,
                    user_input=state.user_input,
                    all_round_outputs=state.specialist_outputs,
                    current_round=state.current_round,
                )
                if event_sink:
                    await event_sink("manager_think", {
                        "phase": "evaluation",
                        "round": state.current_round,
                        "decision": "continue" if eval_decision.should_continue else "synthesize"
                    })

                if not eval_decision.should_continue:
                    break
                    
            state.current_round += 1

        if state.specialist_outputs:
            if event_sink:
                await event_sink("agent_start", {"agent_name": "Manager", "agent_key": "manager"})
                await event_sink("chunk", {"delta": "---\n\nManager synthesis:\n"})
            try:
                # Always stream synthesis if event sinks exist, as it has no tools.
                if event_sink:
                    synth_stream = await self._llm_gateway.stream(
                        GatewayRequest(
                            model_alias=manager_alias,
                            messages=build_orchestrator_synthesis_messages(
                                user_input=state.user_input,
                                specialist_outputs=state.specialist_outputs,
                            ),
                            max_output_tokens=state.max_output_tokens,
                        )
                    )
                    synth_parts = []
                    async for delta in synth_stream.chunks:
                        synth_parts.append(delta)
                        await event_sink("chunk", {"delta": delta})
                        
                    synthesis_result_text = "".join(synth_parts).strip()
                    usage_obj = await synth_stream.usage_future
                    provider_model = await synth_stream.provider_model_future
                else:
                    synthesis_result = await generate_orchestrator_synthesis(
                        gateway=self._llm_gateway,
                        manager_model_alias=manager_alias,
                        user_input=state.user_input,
                        specialist_outputs=state.specialist_outputs,
                        max_output_tokens=state.max_output_tokens,
                    )
                    synthesis_result_text = synthesis_result.text.strip()
                    provider_model = synthesis_result.response.provider_model
                    usage_obj = synthesis_result.response.usage

                state.final_synthesis = synthesis_result_text
                state.usage_entries.append((
                    None,
                    manager_alias,
                    provider_model,
                    usage_obj.input_tokens_fresh,
                    usage_obj.input_tokens_cached,
                    usage_obj.output_tokens,
                    usage_obj.total_tokens
                ))
            except Exception as exc:
                state.current_status = "partial"
                err_msg = f"[[manager_synthesis_error]] {exc}"
                state.final_synthesis = err_msg
                if event_sink:
                    await event_sink("chunk", {"delta": err_msg})

_cached_executor = PurePythonModeExecutor(llm_gateway=get_llm_gateway())

def get_mode_executor():
    return _cached_executor
