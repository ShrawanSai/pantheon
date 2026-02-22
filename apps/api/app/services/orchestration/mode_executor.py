from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import TypedDict

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


@dataclass(frozen=True)
class TurnExecutionInput:
    model_alias: str
    messages: list[GatewayMessage]
    max_output_tokens: int
    thread_id: str


@dataclass(frozen=True)
class TurnExecutionOutput:
    text: str
    provider_model: str
    usage: GatewayUsage


class LangGraphModeExecutor:
    def __init__(self, llm_gateway: LlmGateway) -> None:
        self._llm_gateway = llm_gateway
        self._graph = self._compile_graph()

    def _compile_graph(self):
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

        graph = StateGraph(TurnExecutionState)
        graph.add_node("call_model", call_model)
        graph.set_entry_point("call_model")
        graph.add_edge("call_model", END)
        return graph.compile(checkpointer=_build_checkpointer())

    async def run_turn(self, db: AsyncSession, payload: TurnExecutionInput) -> TurnExecutionOutput:
        _ = db  # Reserved for future graph nodes that persist checkpoint metadata.
        result = await self._graph.ainvoke(
            {
                "model_alias": payload.model_alias,
                "messages": payload.messages,
                "max_output_tokens": payload.max_output_tokens,
            },
            config={"configurable": {"thread_id": payload.thread_id}},
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
        )


def _build_checkpointer():
    # Week 4 baseline: MemorySaver for local/test determinism.
    # Postgres checkpointer wiring is enabled when langgraph-postgres package is available.
    try:
        from langgraph.checkpoint.postgres import PostgresSaver  # type: ignore
        from apps.api.app.db.session import _raw_database_pool_url  # local helper import

        checkpointer = PostgresSaver.from_conn_string(_raw_database_pool_url())
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
def _get_cached_mode_executor() -> LangGraphModeExecutor:
    return LangGraphModeExecutor(llm_gateway=get_llm_gateway())


def get_mode_executor() -> LangGraphModeExecutor:
    return _get_cached_mode_executor()
