from __future__ import annotations

import json
import logging
from math import ceil
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.prebuilt import create_react_agent
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.services.llm.gateway import (
    GatewayMessage,
    GatewayRequest,
    GatewayUsage,
    LlmGateway,
)
from apps.api.app.services.orchestration.mode_executor import ToolCallRecord, TurnExecutionInput, TurnExecutionOutput
from apps.api.app.services.tools.file_tool import FileReadTool, TOOL_NAME as FILE_TOOL_NAME
from apps.api.app.services.tools.react_tools import (
    ToolInvocationTelemetry,
    make_read_file_tool,
    make_web_search_tool,
)
from apps.api.app.services.tools.search_tool import SearchTool, TOOL_NAME as SEARCH_TOOL_NAME
from pantheon_llm.openrouter_langchain import SUPPORTED_LLMS, get_chat_model

_LOGGER = logging.getLogger(__name__)


def _estimate_tokens(text: str) -> int:
    return max(1, ceil(len(text) / 4 * 1.25))


def _to_langchain_messages(messages: list[GatewayMessage]) -> list[BaseMessage]:
    converted: list[BaseMessage] = []
    for message in messages:
        if message.role == "system":
            converted.append(SystemMessage(content=message.content))
        elif message.role == "assistant":
            converted.append(AIMessage(content=message.content))
        else:
            converted.append(HumanMessage(content=message.content))
    return converted


def _extract_text_from_message(message: BaseMessage | None) -> str:
    if message is None:
        return ""
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, str):
                chunks.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                chunks.append(item["text"])
        return " ".join(part.strip() for part in chunks if part and part.strip()).strip()
    return str(content).strip()


def _extract_final_ai_message(messages: list[BaseMessage]) -> AIMessage | None:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            tool_calls = getattr(message, "tool_calls", None) or []
            if tool_calls:
                continue
            return message
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return message
    return None


def _extract_usage(message: AIMessage | None, *, fallback_messages: list[GatewayMessage], fallback_text: str) -> GatewayUsage:
    if message is None:
        input_tokens = sum(_estimate_tokens(item.content) for item in fallback_messages)
        output_tokens = _estimate_tokens(fallback_text)
        return GatewayUsage(
            input_tokens_fresh=input_tokens,
            input_tokens_cached=0,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        )

    usage_metadata: dict[str, Any] = getattr(message, "usage_metadata", {}) or {}
    input_tokens = int(usage_metadata.get("input_tokens") or 0)
    output_tokens = int(usage_metadata.get("output_tokens") or 0)
    total_tokens = int(usage_metadata.get("total_tokens") or 0)
    input_details: dict[str, Any] = usage_metadata.get("input_token_details") or {}
    cached_tokens = int(input_details.get("cache_read") or input_details.get("cached_tokens") or 0)

    text = _extract_text_from_message(message)
    if input_tokens <= 0:
        input_tokens = sum(_estimate_tokens(item.content) for item in fallback_messages)
    if output_tokens <= 0:
        output_tokens = _estimate_tokens(text)
    if total_tokens <= 0:
        total_tokens = input_tokens + output_tokens

    fresh_tokens = max(input_tokens - cached_tokens, 0)
    return GatewayUsage(
        input_tokens_fresh=fresh_tokens,
        input_tokens_cached=max(cached_tokens, 0),
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )


def _extract_provider_model(message: AIMessage | None, model_alias: str) -> str:
    if message is not None:
        metadata = getattr(message, "response_metadata", {}) or {}
        model_name = metadata.get("model_name")
        if isinstance(model_name, str) and model_name.strip():
            return model_name
    spec = SUPPORTED_LLMS.get(model_alias)
    return spec.model_id if spec is not None else model_alias


def _telemetry_to_tool_calls(telemetry: list[ToolInvocationTelemetry]) -> tuple[ToolCallRecord, ...]:
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


class ReactAgentExecutor:
    def __init__(
        self,
        llm_gateway: LlmGateway,
        search_tool: SearchTool,
        file_read_tool: FileReadTool,
    ) -> None:
        self._llm_gateway = llm_gateway
        self._search_tool = search_tool
        self._file_read_tool = file_read_tool

    async def _run_direct(self, payload: TurnExecutionInput) -> TurnExecutionOutput:
        response = await self._llm_gateway.generate(
            GatewayRequest(
                model_alias=payload.model_alias,
                messages=payload.messages,
                max_output_tokens=payload.max_output_tokens,
            )
        )
        return TurnExecutionOutput(
            text=response.text,
            provider_model=response.provider_model,
            usage=response.usage,
            tool_calls=(),
        )

    async def run_turn(self, db: AsyncSession, payload: TurnExecutionInput) -> TurnExecutionOutput:
        allowed_tools = {name.strip().lower() for name in payload.allowed_tool_names if name and name.strip()}
        if not allowed_tools:
            return await self._run_direct(payload)

        telemetry: list[ToolInvocationTelemetry] = []
        tools: list[Any] = []
        if SEARCH_TOOL_NAME in allowed_tools:
            tools.append(
                make_web_search_tool(
                    user_id="",
                    session_id="",
                    turn_id="",
                    agent_key=None,
                    room_id=payload.room_id or None,
                    db=db,
                    search_tool=self._search_tool,
                    telemetry_sink=telemetry.append,
                )
            )
        if FILE_TOOL_NAME in allowed_tools:
            tools.append(
                make_read_file_tool(
                    user_id="",
                    session_id="",
                    turn_id="",
                    agent_key=None,
                    room_id=payload.room_id or None,
                    db=db,
                    file_tool=self._file_read_tool,
                    telemetry_sink=telemetry.append,
                )
            )

        if not tools:
            return await self._run_direct(payload)

        lc_messages = _to_langchain_messages(payload.messages)
        try:
            model = get_chat_model(alias=payload.model_alias, max_tokens=payload.max_output_tokens)
            agent = create_react_agent(model=model, tools=tools)
            result = await agent.ainvoke({"messages": lc_messages})
            all_messages = result.get("messages") if isinstance(result, dict) else None
            if not isinstance(all_messages, list):
                all_messages = []
        except Exception as exc:
            _LOGGER.warning(
                "ReAct execution failed for model '%s'; falling back to direct gateway call. error=%s",
                payload.model_alias,
                exc,
            )
            return await self._run_direct(payload)

        final_ai = _extract_final_ai_message(all_messages)
        final_text = _extract_text_from_message(final_ai)
        usage = _extract_usage(final_ai, fallback_messages=payload.messages, fallback_text=final_text)
        provider_model = _extract_provider_model(final_ai, payload.model_alias)
        tool_calls = _telemetry_to_tool_calls(telemetry)
        return TurnExecutionOutput(
            text=final_text,
            provider_model=provider_model,
            usage=usage,
            tool_calls=tool_calls,
        )
