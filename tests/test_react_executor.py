from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from apps.api.app.services.llm.gateway import GatewayMessage, GatewayRequest, GatewayResponse, GatewayUsage
from apps.api.app.services.orchestration.mode_executor import TurnExecutionInput
from apps.api.app.services.orchestration.react_executor import ReactAgentExecutor
from apps.api.app.services.tools.search_tool import SearchResult


@dataclass
class FakeGateway:
    calls: list[GatewayRequest] = field(default_factory=list)

    async def generate(self, request: GatewayRequest) -> GatewayResponse:
        self.calls.append(request)
        return GatewayResponse(
            text="direct-response",
            provider_model="fake/direct",
            usage=GatewayUsage(
                input_tokens_fresh=10,
                input_tokens_cached=0,
                output_tokens=5,
                total_tokens=15,
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
                title="A",
                url="https://example.com",
                snippet="snippet",
            )
        ]


@dataclass
class FakeFileReadTool:
    calls: list[tuple[str, str | None]] = field(default_factory=list)

    async def read(self, *, file_id: str, room_id: str, db):
        _ = db
        self.calls.append((file_id, room_id))
        return type("Result", (), {"status": "completed", "content": "file text", "error": None})()


class ReactExecutorTests(unittest.TestCase):
    def test_react_agent_invokes_search_tool(self) -> None:
        gateway = FakeGateway()
        search_tool = FakeSearchTool()
        file_tool = FakeFileReadTool()
        executor = ReactAgentExecutor(gateway, search_tool, file_tool)

        class StubAgent:
            async def ainvoke(self, payload):
                tools = stub_create.tools
                search_result = await tools[0].ainvoke({"query": "latest ai"})
                _ = payload
                return {
                    "messages": [
                        HumanMessage(content="search this"),
                        AIMessage(
                            content="",
                            tool_calls=[
                                {
                                    "name": "search",
                                    "args": {"query": "latest ai"},
                                    "id": "call_1",
                                    "type": "tool_call",
                                }
                            ],
                        ),
                        ToolMessage(content=search_result, tool_call_id="call_1"),
                        AIMessage(
                            content="final answer",
                            response_metadata={"model_name": "fake/react-model"},
                            usage_metadata={"input_tokens": 12, "output_tokens": 8, "total_tokens": 20},
                        ),
                    ]
                }

        def stub_create(*, model, tools):
            _ = model
            stub_create.tools = tools
            return StubAgent()

        with patch("apps.api.app.services.orchestration.react_executor.get_chat_model", return_value=object()):
            with patch("apps.api.app.services.orchestration.react_executor.create_react_agent", side_effect=stub_create):
                output = asyncio.run(
                    executor.run_turn(
                        db=None,  # type: ignore[arg-type]
                        payload=TurnExecutionInput(
                            model_alias="deepseek",
                            messages=[GatewayMessage(role="user", content="search for latest ai")],
                            max_output_tokens=256,
                            thread_id="t1",
                            allowed_tool_names=("search",),
                        ),
                    )
                )

        self.assertEqual(search_tool.calls, ["latest ai"])
        self.assertEqual(output.text, "final answer")
        self.assertEqual(output.provider_model, "fake/react-model")
        self.assertEqual(len(output.tool_calls), 1)
        self.assertEqual(output.tool_calls[0].tool_name, "search")

    def test_react_agent_invokes_file_tool(self) -> None:
        gateway = FakeGateway()
        search_tool = FakeSearchTool()
        file_tool = FakeFileReadTool()
        executor = ReactAgentExecutor(gateway, search_tool, file_tool)

        class StubAgent:
            async def ainvoke(self, payload):
                tools = stub_create.tools
                file_result = await tools[0].ainvoke({"file_id": "file-1"})
                _ = payload
                return {
                    "messages": [
                        HumanMessage(content="read file"),
                        AIMessage(
                            content="",
                            tool_calls=[
                                {
                                    "name": "file_read",
                                    "args": {"file_id": "file-1"},
                                    "id": "call_2",
                                    "type": "tool_call",
                                }
                            ],
                        ),
                        ToolMessage(content=file_result, tool_call_id="call_2"),
                        AIMessage(
                            content="done",
                            response_metadata={"model_name": "fake/react-model"},
                            usage_metadata={"input_tokens": 10, "output_tokens": 6, "total_tokens": 16},
                        ),
                    ]
                }

        def stub_create(*, model, tools):
            _ = model
            stub_create.tools = tools
            return StubAgent()

        with patch("apps.api.app.services.orchestration.react_executor.get_chat_model", return_value=object()):
            with patch("apps.api.app.services.orchestration.react_executor.create_react_agent", side_effect=stub_create):
                output = asyncio.run(
                    executor.run_turn(
                        db=None,  # type: ignore[arg-type]
                        payload=TurnExecutionInput(
                            model_alias="deepseek",
                            messages=[GatewayMessage(role="user", content="read this file")],
                            max_output_tokens=256,
                            thread_id="t2",
                            allowed_tool_names=("file_read",),
                            room_id="room-1",
                        ),
                    )
                )

        self.assertEqual(file_tool.calls, [("file-1", "room-1")])
        self.assertEqual(output.text, "done")
        self.assertEqual(len(output.tool_calls), 1)
        self.assertEqual(output.tool_calls[0].tool_name, "file_read")

    def test_react_agent_no_tool_call(self) -> None:
        gateway = FakeGateway()
        search_tool = FakeSearchTool()
        file_tool = FakeFileReadTool()
        executor = ReactAgentExecutor(gateway, search_tool, file_tool)

        class StubAgent:
            async def ainvoke(self, payload):
                _ = payload
                return {
                    "messages": [
                        HumanMessage(content="hello"),
                        AIMessage(
                            content="plain answer",
                            response_metadata={"model_name": "fake/react-model"},
                            usage_metadata={"input_tokens": 7, "output_tokens": 5, "total_tokens": 12},
                        ),
                    ]
                }

        with patch("apps.api.app.services.orchestration.react_executor.get_chat_model", return_value=object()):
            with patch("apps.api.app.services.orchestration.react_executor.create_react_agent", return_value=StubAgent()):
                output = asyncio.run(
                    executor.run_turn(
                        db=None,  # type: ignore[arg-type]
                        payload=TurnExecutionInput(
                            model_alias="deepseek",
                            messages=[GatewayMessage(role="user", content="hello")],
                            max_output_tokens=256,
                            thread_id="t3",
                            allowed_tool_names=("search",),
                        ),
                    )
                )

        self.assertEqual(output.text, "plain answer")
        self.assertEqual(output.tool_calls, ())

    def test_react_agent_empty_allowed_tools(self) -> None:
        gateway = FakeGateway()
        search_tool = FakeSearchTool()
        file_tool = FakeFileReadTool()
        executor = ReactAgentExecutor(gateway, search_tool, file_tool)

        output = asyncio.run(
            executor.run_turn(
                db=None,  # type: ignore[arg-type]
                payload=TurnExecutionInput(
                    model_alias="deepseek",
                    messages=[GatewayMessage(role="user", content="no tools")],
                    max_output_tokens=256,
                    thread_id="t4",
                    allowed_tool_names=(),
                ),
            )
        )

        self.assertEqual(len(gateway.calls), 1)
        self.assertEqual(output.text, "direct-response")
        self.assertEqual(output.tool_calls, ())


if __name__ == "__main__":
    unittest.main()
