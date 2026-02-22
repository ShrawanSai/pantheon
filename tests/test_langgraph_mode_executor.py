from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
import sys
import types
import unittest
from uuid import uuid4
from unittest.mock import patch

from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from apps.api.app.db.models import Base, Room, UploadedFile, User
from apps.api.app.services.llm.gateway import GatewayMessage, GatewayResponse, GatewayUsage
from apps.api.app.services.orchestration import mode_executor
from apps.api.app.services.orchestration.mode_executor import (
    LangGraphModeExecutor,
    TurnExecutionInput,
)
from apps.api.app.services.tools.file_tool import DefaultFileReadTool
from apps.api.app.services.tools.search_tool import SearchResult

# Keep import-time settings self-contained for CI/local test runs.
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "dummy-service-role-key")
os.environ.setdefault("API_CORS_ALLOWED_ORIGINS", "http://localhost:3000")


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
        class FakeBaseCheckpointSaver:
            pass

        class FakePostgresSaver(FakeBaseCheckpointSaver):
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
        base_module = types.ModuleType("langgraph.checkpoint.base")
        base_module.BaseCheckpointSaver = FakeBaseCheckpointSaver

        with patch.dict(
            sys.modules,
            {
                "langgraph.checkpoint.postgres": postgres_module,
                "langgraph.checkpoint.base": base_module,
            },
        ):
            with patch("apps.api.app.db.session._raw_database_pool_url", return_value="postgresql://example/db"):
                mode_executor._POSTGRES_CHECKPOINTER_SETUP_DONE = False
                first = mode_executor._build_checkpointer()
                second = mode_executor._build_checkpointer()
        self.assertIsInstance(first, FakePostgresSaver)
        self.assertIsInstance(second, FakePostgresSaver)
        self.assertEqual(first.setup_calls, 1)
        self.assertEqual(second.setup_calls, 0)

    def test_build_checkpointer_falls_back_when_postgres_factory_returns_context_manager(self) -> None:
        class FakeContextManager:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                _ = (exc_type, exc, tb)
                return False

        class FakePostgresSaver:
            @classmethod
            def from_conn_string(cls, conn_str: str):
                _ = conn_str
                return FakeContextManager()

        class FakeBaseCheckpointSaver:
            pass

        postgres_module = types.ModuleType("langgraph.checkpoint.postgres")
        postgres_module.PostgresSaver = FakePostgresSaver
        base_module = types.ModuleType("langgraph.checkpoint.base")
        base_module.BaseCheckpointSaver = FakeBaseCheckpointSaver

        with patch.dict(
            sys.modules,
            {
                "langgraph.checkpoint.postgres": postgres_module,
                "langgraph.checkpoint.base": base_module,
            },
        ):
            with patch("apps.api.app.db.session._raw_database_pool_url", return_value="postgresql://example/db"):
                with patch.object(mode_executor, "_LOGGER") as logger:
                    mode_executor._POSTGRES_CHECKPOINTER_SETUP_DONE = False
                    checkpointer = mode_executor._build_checkpointer()

        self.assertIsInstance(checkpointer, MemorySaver)
        logger.warning.assert_called()


class FileReadNodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.session_factory = async_sessionmaker(
            bind=cls.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

        async def init_db() -> None:
            async with cls.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

        asyncio.run(init_db())

    @classmethod
    def tearDownClass(cls) -> None:
        async def shutdown_db() -> None:
            async with cls.engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            await cls.engine.dispose()

        asyncio.run(shutdown_db())

    def _seed_uploaded_file(self, *, parse_status: str, parsed_text: str | None = None) -> tuple[str, str]:
        file_id = str(uuid4())
        room_id = str(uuid4())
        user_id = str(uuid4())

        async def insert_rows() -> None:
            async with self.session_factory() as session:
                session.add(User(id=user_id, email=f"{user_id}@example.com"))
                session.add(
                    Room(
                        id=room_id,
                        owner_user_id=user_id,
                        name="File Read Room",
                        goal=None,
                        current_mode="orchestrator",
                        pending_mode=None,
                    )
                )
                session.add(
                    UploadedFile(
                        id=file_id,
                        user_id=user_id,
                        room_id=room_id,
                        filename="notes.txt",
                        storage_key=f"rooms/{room_id}/{file_id}/notes.txt",
                        content_type="text/plain",
                        file_size=15,
                        parse_status=parse_status,
                        parsed_text=parsed_text,
                        error_message="parse failed" if parse_status == "failed" else None,
                    )
                )
                await session.commit()

        asyncio.run(insert_rows())
        return file_id, room_id

    def test_file_read_permitted_and_completed(self) -> None:
        gateway = FakeGateway()
        executor = LangGraphModeExecutor(
            llm_gateway=gateway,
            search_tool=FakeSearchTool(),
            file_read_tool=DefaultFileReadTool(),
        )
        file_id, room_id = self._seed_uploaded_file(parse_status="completed", parsed_text="test content")

        async def run() -> None:
            async with self.session_factory() as session:
                return await executor.run_turn(
                    db=session,
                    payload=TurnExecutionInput(
                        model_alias="deepseek",
                        messages=[GatewayMessage(role="user", content=f"file: {file_id}")],
                        max_output_tokens=256,
                        thread_id="file-thread-1",
                        allowed_tool_names=("file_read",),
                        room_id=room_id,
                    ),
                )

        output = asyncio.run(run())
        self.assertEqual(len(output.tool_calls), 1)
        self.assertEqual(output.tool_calls[0].tool_name, "file_read")
        self.assertEqual(output.tool_calls[0].status, "success")
        self.assertEqual(len(gateway.calls), 1)
        self.assertTrue(any("Tool(file_read) content" in message.content for message in gateway.calls[0]))

    def test_file_read_permitted_and_pending(self) -> None:
        gateway = FakeGateway()
        executor = LangGraphModeExecutor(
            llm_gateway=gateway,
            search_tool=FakeSearchTool(),
            file_read_tool=DefaultFileReadTool(),
        )
        file_id, room_id = self._seed_uploaded_file(parse_status="pending")

        async def run() -> None:
            async with self.session_factory() as session:
                return await executor.run_turn(
                    db=session,
                    payload=TurnExecutionInput(
                        model_alias="deepseek",
                        messages=[GatewayMessage(role="user", content=f"file: {file_id}")],
                        max_output_tokens=256,
                        thread_id="file-thread-2",
                        allowed_tool_names=("file_read",),
                        room_id=room_id,
                    ),
                )

        output = asyncio.run(run())
        self.assertEqual(len(output.tool_calls), 1)
        self.assertEqual(output.tool_calls[0].status, "error")
        self.assertEqual(len(gateway.calls), 1)
        self.assertFalse(any("Tool(file_read) content" in message.content for message in gateway.calls[0]))

    def test_file_read_not_permitted_node_absent(self) -> None:
        gateway = FakeGateway()
        executor = LangGraphModeExecutor(
            llm_gateway=gateway,
            search_tool=FakeSearchTool(),
            file_read_tool=DefaultFileReadTool(),
        )

        async def run() -> None:
            return await executor.run_turn(
                db=None,  # type: ignore[arg-type]
                payload=TurnExecutionInput(
                    model_alias="deepseek",
                    messages=[GatewayMessage(role="user", content=f"file: {uuid4()}")],
                    max_output_tokens=256,
                    thread_id="file-thread-3",
                    allowed_tool_names=(),
                    room_id="room-ignored",
                ),
            )

        output = asyncio.run(run())
        self.assertEqual(output.tool_calls, ())
        self.assertEqual(len(gateway.calls), 1)
        self.assertFalse(any("Tool(file_read) content" in message.content for message in gateway.calls[0]))


if __name__ == "__main__":
    unittest.main()
