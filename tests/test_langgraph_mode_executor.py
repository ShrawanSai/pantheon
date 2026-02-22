from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
import sys
import types
import unittest
from unittest.mock import patch

from langgraph.checkpoint.memory import MemorySaver
from apps.api.app.services.llm.gateway import GatewayMessage, GatewayResponse, GatewayUsage
from apps.api.app.services.orchestration import mode_executor
from apps.api.app.services.orchestration.mode_executor import (
    LangGraphModeExecutor,
    TurnExecutionInput,
)
from apps.api.app.services.tools.search_tool import SearchResult


@dataclass
class FakeGateway:
    calls: list[list[GatewayMessage]] = field(default_factory=list)

    async def generate(self, request):
        self.calls.append(request.messages)
        return GatewayResponse(
            text="graph-response",
            provider_model="fake/graph-model",
            usage=GatewayUsage(
                input_tokens_fresh=11,
                input_tokens_cached=0,
                output_tokens=7,
                total_tokens=18,
            ),
        )


@dataclass
class FakeSearchTool:
    calls: list[str] = field(default_factory=list)

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        _ = max_results
        self.calls.append(query)
        return [
            SearchResult(
                title="Result A",
                url="https://example.com/a",
                snippet="Snippet A",
            )
        ]


class LangGraphModeExecutorTests(unittest.TestCase):
    def test_run_turn_executes_langgraph_node_and_returns_gateway_payload(self) -> None:
        gateway = FakeGateway()
        executor = LangGraphModeExecutor(llm_gateway=gateway)

        async def run():
            return await executor.run_turn(
                db=None,  # type: ignore[arg-type]
                payload=TurnExecutionInput(
                    model_alias="deepseek",
                    messages=[
                        GatewayMessage(role="system", content="s"),
                        GatewayMessage(role="user", content="u"),
                    ],
                    max_output_tokens=256,
                    thread_id="thread-1",
                ),
            )

        output = asyncio.run(run())
        self.assertEqual(output.text, "graph-response")
        self.assertEqual(output.provider_model, "fake/graph-model")
        self.assertEqual(output.usage.total_tokens, 18)
        self.assertEqual(len(gateway.calls), 1)

    def test_run_turn_uses_search_tool_when_permitted_and_query_present(self) -> None:
        gateway = FakeGateway()
        search_tool = FakeSearchTool()
        executor = LangGraphModeExecutor(llm_gateway=gateway, search_tool=search_tool)

        async def run():
            return await executor.run_turn(
                db=None,  # type: ignore[arg-type]
                payload=TurnExecutionInput(
                    model_alias="deepseek",
                    messages=[
                        GatewayMessage(role="system", content="s"),
                        GatewayMessage(role="user", content="search: latest ai news"),
                    ],
                    max_output_tokens=256,
                    thread_id="thread-search-1",
                    allowed_tool_names=("search",),
                ),
            )

        output = asyncio.run(run())
        self.assertEqual(output.text, "graph-response")
        self.assertEqual(search_tool.calls, ["latest ai news"])
        self.assertEqual(len(gateway.calls), 1)
        injected_messages = gateway.calls[0]
        self.assertTrue(any("Tool(search) results" in message.content for message in injected_messages))
        self.assertEqual(len(output.tool_calls), 1)
        tool_call = output.tool_calls[0]
        self.assertEqual(tool_call.tool_name, "search")
        self.assertEqual(tool_call.status, "success")
        self.assertIsNotNone(tool_call.latency_ms)
        json.loads(tool_call.input_json)
        json.loads(tool_call.output_json)

    def test_run_turn_does_not_use_search_tool_when_not_permitted(self) -> None:
        gateway = FakeGateway()
        search_tool = FakeSearchTool()
        executor = LangGraphModeExecutor(llm_gateway=gateway, search_tool=search_tool)

        async def run():
            return await executor.run_turn(
                db=None,  # type: ignore[arg-type]
                payload=TurnExecutionInput(
                    model_alias="deepseek",
                    messages=[
                        GatewayMessage(role="system", content="s"),
                        GatewayMessage(role="user", content="search: latest ai news"),
                    ],
                    max_output_tokens=256,
                    thread_id="thread-search-2",
                    allowed_tool_names=(),
                ),
            )

        output = asyncio.run(run())
        self.assertEqual(output.text, "graph-response")
        self.assertEqual(search_tool.calls, [])
        self.assertEqual(len(gateway.calls), 1)
        injected_messages = gateway.calls[0]
        self.assertFalse(any("Tool(search) results" in message.content for message in injected_messages))
        self.assertEqual(output.tool_calls, ())

    def test_build_checkpointer_logs_warning_and_uses_memory_fallback(self) -> None:
        with patch.object(mode_executor, "_LOGGER") as logger:
            mode_executor._POSTGRES_CHECKPOINTER_SETUP_DONE = False
            checkpointer = mode_executor._build_checkpointer()
        self.assertIsInstance(checkpointer, MemorySaver)
        logger.warning.assert_called()

    def test_build_checkpointer_runs_setup_once_when_postgres_saver_available(self) -> None:
        class FakePostgresSaver:
            def __init__(self) -> None:
                self.setup_calls = 0

            @classmethod
            def from_conn_string(cls, conn_str: str):
                _ = conn_str
                return cls()

            def setup(self) -> None:
                self.setup_calls += 1

        postgres_module = types.ModuleType("langgraph.checkpoint.postgres")
        postgres_module.PostgresSaver = FakePostgresSaver

        with patch.dict(sys.modules, {"langgraph.checkpoint.postgres": postgres_module}):
            with patch("apps.api.app.db.session._raw_database_pool_url", return_value="postgresql://example/db"):
                mode_executor._POSTGRES_CHECKPOINTER_SETUP_DONE = False
                first = mode_executor._build_checkpointer()
                second = mode_executor._build_checkpointer()
        self.assertIsInstance(first, FakePostgresSaver)
        self.assertIsInstance(second, FakePostgresSaver)
        self.assertEqual(first.setup_calls, 1)
        self.assertEqual(second.setup_calls, 0)


if __name__ == "__main__":
    unittest.main()
