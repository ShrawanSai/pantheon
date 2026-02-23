from __future__ import annotations

import asyncio
import json
import inspect
import logging
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.services.llm.gateway import (
    GatewayMessage,
    GatewayRequest,
    GatewayUsage,
    LlmGateway,
    get_llm_gateway,
)
from apps.api.app.services.tools.file_tool import (
    FileReadTool,
    TOOL_NAME as FILE_READ_TOOL_NAME,
    get_file_read_tool,
)
from apps.api.app.services.tools.search_tool import SearchTool, TOOL_NAME as SEARCH_TOOL_NAME, get_search_tool

_LOGGER = logging.getLogger(__name__)
_POSTGRES_CHECKPOINTER_SETUP_DONE = False


class TurnExecutionState(TypedDict, total=False):
    model_alias: str
    messages: list[GatewayMessage]
    max_output_tokens: int
    provider_model: str
    text: str
    usage_input_tokens_fresh: int
    usage_input_tokens_cached: int
    usage_output_tokens: int
    usage_total_tokens: int
    tool_query: str | None
    room_id: str
    file_id_trigger: str | None
    tool_events: list[dict[str, object]]


@dataclass(frozen=True)
class TurnExecutionInput:
    model_alias: str
    messages: list[GatewayMessage]
    max_output_tokens: int
    thread_id: str
    allowed_tool_names: tuple[str, ...] = ()
    room_id: str = ""


@dataclass(frozen=True)
class TurnExecutionOutput:
    text: str
    provider_model: str
    usage: GatewayUsage
    tool_calls: tuple["ToolCallRecord", ...] = ()


@dataclass(frozen=True)
class ToolCallRecord:
    tool_name: str
    input_json: str
    output_json: str
    status: str
    latency_ms: int | None
    tool_call_id: str | None = None


class TurnExecutor(Protocol):
    async def run_turn(self, db: AsyncSession, payload: TurnExecutionInput) -> TurnExecutionOutput: ...


class LangGraphModeExecutor:
    def __init__(
        self,
        llm_gateway: LlmGateway,
        search_tool: SearchTool | None = None,
        file_read_tool: FileReadTool | None = None,
    ) -> None:
        self._llm_gateway = llm_gateway
        self._search_tool = search_tool or get_search_tool()
        self._file_read_tool = file_read_tool or get_file_read_tool()
        self._graphs: dict[tuple[str, ...], object] = {}

    def _extract_search_query(self, messages: list[GatewayMessage]) -> str | None:
        user_messages = [message.content.strip() for message in messages if message.role == "user" and message.content.strip()]
        for latest in reversed(user_messages):
            lowered = latest.lower()
            if lowered.startswith("search:"):
                query = latest.split(":", 1)[1].strip()
                return query or None
            if lowered.startswith("search for "):
                query = latest[len("search for ") :].strip()
                return query or None
        return None

    def _extract_file_id(self, messages: list[GatewayMessage]) -> str | None:
        user_messages = [message.content.strip() for message in messages if message.role == "user" and message.content.strip()]
        for latest in reversed(user_messages):
            if latest.lower().startswith("file:"):
                file_id = latest.split(":", 1)[1].strip()
                return file_id or None
        return None

    def _compile_graph(self, allowed_tools: set[str], db: AsyncSession | None = None):
        async def call_model(state: TurnExecutionState) -> TurnExecutionState:
            response = await self._llm_gateway.generate(
                GatewayRequest(
                    model_alias=state["model_alias"],
                    messages=state["messages"],
                    max_output_tokens=state["max_output_tokens"],
                )
            )
            return {
                "provider_model": response.provider_model,
                "text": response.text,
                "usage_input_tokens_fresh": response.usage.input_tokens_fresh,
                "usage_input_tokens_cached": response.usage.input_tokens_cached,
                "usage_output_tokens": response.usage.output_tokens,
                "usage_total_tokens": response.usage.total_tokens,
            }

        async def maybe_search(state: TurnExecutionState) -> TurnExecutionState:
            query = state.get("tool_query")
            if not query:
                return {}
            started = time.monotonic()
            try:
                results = await self._search_tool.search(query=query, max_results=5)
                latency_ms = int((time.monotonic() - started) * 1000)
                lines: list[str] = []
                for item in results:
                    title = item.title or "(untitled)"
                    url = item.url or "(no-url)"
                    snippet = item.snippet or ""
                    lines.append(f"- {title} | {url} | {snippet}")
                tool_text = "\n".join(lines) if lines else "- No search results returned."
                enriched_messages = [
                    *state["messages"],
                    GatewayMessage(
                        role="system",
                        content=f"Tool({SEARCH_TOOL_NAME}) results for query '{query}':\n{tool_text}",
                    ),
                ]
                tool_event = {
                    "tool_name": SEARCH_TOOL_NAME,
                    "input_json": json.dumps({"query": query}),
                    "output_json": json.dumps({"result_count": len(results)}),
                    "status": "success",
                    "latency_ms": latency_ms,
                }
                existing_events = state.get("tool_events") or []
                return {"messages": enriched_messages, "tool_events": [*existing_events, tool_event]}
            except Exception as exc:
                latency_ms = int((time.monotonic() - started) * 1000)
                tool_event = {
                    "tool_name": SEARCH_TOOL_NAME,
                    "input_json": json.dumps({"query": query}),
                    "output_json": json.dumps({"error": str(exc)}),
                    "status": "error",
                    "latency_ms": latency_ms,
                }
                existing_events = state.get("tool_events") or []
                return {"tool_events": [*existing_events, tool_event]}

        async def maybe_file_read(state: TurnExecutionState) -> TurnExecutionState:
            file_id = state.get("file_id_trigger")
            if not file_id:
                return {}
            room_id = state.get("room_id") or ""
            started = time.monotonic()
            try:
                if db is None:
                    raise RuntimeError("DB session unavailable for file_read tool.")
                result = await self._file_read_tool.read(file_id=file_id, room_id=room_id, db=db)
            except Exception as exc:
                latency_ms = int((time.monotonic() - started) * 1000)
                tool_event = {
                    "tool_name": FILE_READ_TOOL_NAME,
                    "input_json": json.dumps({"file_id": file_id}),
                    "output_json": json.dumps({"error": str(exc)}),
                    "status": "error",
                    "latency_ms": latency_ms,
                }
                existing_events = state.get("tool_events") or []
                return {"tool_events": [*existing_events, tool_event]}

            latency_ms = int((time.monotonic() - started) * 1000)
            if result.status == "completed":
                enriched_messages = [
                    *state["messages"],
                    GatewayMessage(
                        role="system",
                        content=f"Tool({FILE_READ_TOOL_NAME}) content for file '{file_id}':\n{result.content or ''}",
                    ),
                ]
                tool_event = {
                    "tool_name": FILE_READ_TOOL_NAME,
                    "input_json": json.dumps({"file_id": file_id}),
                    "output_json": json.dumps({"chars": len(result.content or "")}),
                    "status": "success",
                    "latency_ms": latency_ms,
                }
                existing_events = state.get("tool_events") or []
                return {"messages": enriched_messages, "tool_events": [*existing_events, tool_event]}

            tool_event = {
                "tool_name": FILE_READ_TOOL_NAME,
                "input_json": json.dumps({"file_id": file_id}),
                "output_json": json.dumps({"error": result.error, "result_status": result.status}),
                "status": "error",
                "latency_ms": latency_ms,
            }
            existing_events = state.get("tool_events") or []
            return {"tool_events": [*existing_events, tool_event]}

        graph = StateGraph(TurnExecutionState)
        has_search = SEARCH_TOOL_NAME in allowed_tools
        has_file_read = FILE_READ_TOOL_NAME in allowed_tools
        if has_search and has_file_read:
            graph.add_node("maybe_search", maybe_search)
            graph.add_node("maybe_file_read", maybe_file_read)
            graph.add_node("call_model", call_model)
            graph.set_entry_point("maybe_search")
            graph.add_edge("maybe_search", "maybe_file_read")
            graph.add_edge("maybe_file_read", "call_model")
            graph.add_edge("call_model", END)
        elif has_search:
            graph.add_node("maybe_search", maybe_search)
            graph.add_node("call_model", call_model)
            graph.set_entry_point("maybe_search")
            graph.add_edge("maybe_search", "call_model")
            graph.add_edge("call_model", END)
        elif has_file_read:
            graph.add_node("maybe_file_read", maybe_file_read)
            graph.add_node("call_model", call_model)
            graph.set_entry_point("maybe_file_read")
            graph.add_edge("maybe_file_read", "call_model")
            graph.add_edge("call_model", END)
        else:
            graph.add_node("call_model", call_model)
            graph.set_entry_point("call_model")
            graph.add_edge("call_model", END)
        return graph.compile(checkpointer=_build_checkpointer())

    def _get_compiled_graph(self, allowed_tools: set[str], db: AsyncSession | None = None):
        if FILE_READ_TOOL_NAME in allowed_tools:
            return self._compile_graph(allowed_tools, db=db)
        key = tuple(sorted(allowed_tools))
        graph = self._graphs.get(key)
        if graph is None:
            graph = self._compile_graph(allowed_tools, db=None)
            self._graphs[key] = graph
        return graph

    async def run_turn(self, db: AsyncSession, payload: TurnExecutionInput) -> TurnExecutionOutput:
        allowed_tools = {name.strip().lower() for name in payload.allowed_tool_names if name and name.strip()}
        graph = self._get_compiled_graph(allowed_tools, db=db)
        result = await graph.ainvoke(
            {
                "model_alias": payload.model_alias,
                "messages": payload.messages,
                "max_output_tokens": payload.max_output_tokens,
                "tool_query": self._extract_search_query(payload.messages),
                "room_id": payload.room_id,
                "file_id_trigger": self._extract_file_id(payload.messages),
            },
            config={"configurable": {"thread_id": payload.thread_id}},
        )
        raw_tool_events = result.get("tool_events") or []
        tool_calls = tuple(
            ToolCallRecord(
                tool_name=str(event["tool_name"]),
                input_json=str(event["input_json"]),
                output_json=str(event["output_json"]),
                status=str(event["status"]),
                latency_ms=int(event["latency_ms"]) if event.get("latency_ms") is not None else None,
            )
            for event in raw_tool_events
        )
        return TurnExecutionOutput(
            text=result["text"],
            provider_model=result["provider_model"],
            usage=GatewayUsage(
                input_tokens_fresh=result["usage_input_tokens_fresh"],
                input_tokens_cached=result["usage_input_tokens_cached"],
                output_tokens=result["usage_output_tokens"],
                total_tokens=result["usage_total_tokens"],
            ),
            tool_calls=tool_calls,
        )


def _build_checkpointer():
    # Week 4 baseline: MemorySaver for local/test determinism.
    # Postgres checkpointer wiring is enabled when langgraph-postgres package is available.
    try:
        from langgraph.checkpoint.postgres import PostgresSaver  # type: ignore
        from langgraph.checkpoint.base import BaseCheckpointSaver  # type: ignore
        from apps.api.app.db.session import _raw_database_pool_url  # local helper import

        checkpointer = PostgresSaver.from_conn_string(_raw_database_pool_url())
        if not isinstance(checkpointer, BaseCheckpointSaver):
            _LOGGER.warning(
                "Postgres checkpointer factory returned unsupported object type (%s); using MemorySaver.",
                type(checkpointer).__name__,
            )
            return MemorySaver()
        _setup_checkpointer_once(checkpointer)
        _LOGGER.info("Using Postgres checkpointer for LangGraph turn execution.")
        return checkpointer
    except Exception as exc:
        _LOGGER.warning(
            "Postgres checkpointer unavailable; falling back to MemorySaver. reason=%s",
            exc,
        )
        return MemorySaver()


def _setup_checkpointer_once(checkpointer: object) -> None:
    global _POSTGRES_CHECKPOINTER_SETUP_DONE
    if _POSTGRES_CHECKPOINTER_SETUP_DONE:
        return
    setup_fn = getattr(checkpointer, "setup", None)
    if not callable(setup_fn):
        _LOGGER.warning("Postgres checkpointer has no setup() method; skipping setup step.")
        _POSTGRES_CHECKPOINTER_SETUP_DONE = True
        return
    result = setup_fn()
    if inspect.isawaitable(result):
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                _LOGGER.warning("Skipping async checkpointer setup because event loop is already running.")
            else:
                loop.run_until_complete(result)
        except RuntimeError:
            asyncio.run(result)
    _POSTGRES_CHECKPOINTER_SETUP_DONE = True
    _LOGGER.info("Postgres checkpointer setup step completed.")


@lru_cache(maxsize=1)
def _get_cached_mode_executor():
    from apps.api.app.services.orchestration.react_executor import ReactAgentExecutor

    return ReactAgentExecutor(
        llm_gateway=get_llm_gateway(),
        search_tool=get_search_tool(),
        file_read_tool=get_file_read_tool(),
    )


def get_mode_executor():
    return _get_cached_mode_executor()
