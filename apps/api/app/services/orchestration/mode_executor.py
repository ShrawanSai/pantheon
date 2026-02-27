from __future__ import annotations

import asyncio
import json
import logging
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
        base_messages = [
            GatewayMessage(role="system", content=f"Agent role: {agent.role_prompt}"),
            *state.primary_context_messages
        ]
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

        shared_history = []
        for agent in ordered_agents:
            other_names_str = ", ".join(n for n in other_names_lower if n != agent.name.lower())
            other_example = other_names_lower[0].title() if other_names_lower else "OtherAgent"
            base_messages = [
                GatewayMessage(role="system", content=f"Room mode: roundtable\nAgent role: {agent.role_prompt}\n\nCRITICAL: You are {agent.name}. Respond ONLY with your own direct speech. DO NOT include your own name, name tags (like '[{agent.name}]:' or '{agent.name}:'). Start immediately with your content. You are participating in a group conversation; acknowledge the user or previous agent statements if relevant.\n\nCRITICAL INSTRUCTION: When there is a tag to another agent beside you (e.g., @{other_example}), answer ONLY on your behalf. DO NOT write responses, dialogue, or script lines for any other agents ({other_names_str}). When you are finished with your own thought, STOP generating immediately.\n\nBAD EXAMPLE (Roleplaying others):\n[My thought about the topic.]\n\n{other_example}: [Their thought about the topic.]\n\nGOOD EXAMPLE (Answering only for myself):\n[My thought about the topic.]"),
                *state.primary_context_messages,
                *shared_history
            ]
            
            stop_seqs = []
            for n in other_names_lower:
                if n != agent.name.lower():
                    # Stop if the LLM tries to generate another agent's name followed by a colon
                    stop_seqs.extend([f"\n{n.title()}:", f"{n.title()}:", f"\n{n.upper()}:", f"{n.upper()}:"])
            stop_seqs.append("\n---")
            # OpenAI limit is usually 4 stop sequences.
            # We will truncate to 4 sequences max to avoid api errors, prioritizing the common cases.
            stop_seqs = list(set(stop_seqs))[:4]
            
            text, success = await self._invoke_agent(state, agent, base_messages, db, event_sink, stop_sequences=stop_seqs)
            
            # Post-processing: truncate if LLM hallucinates another agent's turn
            if success and text:
                import re
                lines = text.split('\n')
                cutoff_idx = len(lines)
                for i, line in enumerate(lines):
                    line_strip = line.strip()
                    if line_strip == "---" or line_strip.startswith("--- "):
                        cutoff_idx = i
                        break
                    # Match "OtherName:" or "OtherName :"
                    lower_line = line_strip.lower()
                    if any(lower_line.startswith(f"{n}:") or lower_line.startswith(f"[{n}]") or lower_line.startswith(f"{n} says:") for n in other_names_lower if n != agent.name.lower()):
                        # Only cut if it looks like a prefix, not a sentence
                        if len(line_strip) < 100: # heuristic
                            cutoff_idx = i
                            break
                if cutoff_idx < len(lines):
                    text = '\n'.join(lines[:cutoff_idx]).strip()

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

                base_messages = [
                    GatewayMessage(
                        role="system", 
                        content=(
                            f"CRITICAL INSTRUCTION: You are {agent.name}. {agent.role_prompt}\n\n"
                            f"You are currently in a meeting being moderated by an Orchestrating Manager. "
                            f"The Council consists of: {council_list}.\n\n"
                            f"The Manager has specifically called upon YOU ({agent.name}) with these instructions:\n"
                            f"'{instruction}'\n\n"
                            f"RULES:\n"
                            f"1. You MUST stay in character as {agent.name}.\n"
                            f"2. You are NOT the Manager. Do not describe the process, do not moderate the room, do not summarize, and do not assign tasks.\n"
                            f"3. Respond ONLY with your own direct speech, answering the instruction from your unique perspective.\n"
                            f"4. DO NOT include your own name, name tags (like '[{agent.name}]:' or '{agent.name}:'), or narrative actions."
                        )
                    ),
                    *state.primary_context_messages,
                ]

                # If this isn't the first turn, provide the prior outputs so the agent knows what has been discussed
                if state.specialist_outputs:
                    specialist_block = "\n\n".join(f"[{name} just said]:\n{text}" for name, text in state.specialist_outputs)
                    base_messages.append(
                        GatewayMessage(role="user", content=f"Previous specialist outputs in this room:\n{specialist_block}")
                    )
                
                text, success = await self._invoke_agent(state, agent, base_messages, db, event_sink)
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
