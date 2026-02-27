from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Callable, Any

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.services.tools.file_tool import FileReadTool
from apps.api.app.services.tools.search_tool import SearchTool


@dataclass(frozen=True)
class ToolInvocationTelemetry:
    tool_name: str
    input_json: str
    output_json: str
    status: str
    latency_ms: int | None


TelemetrySink = Callable[[ToolInvocationTelemetry], None]


def _emit_telemetry(sink: TelemetrySink | None, telemetry: ToolInvocationTelemetry) -> None:
    if sink is None:
        return
    sink(telemetry)


def make_web_search_tool_execute(
    *,
    search_tool: SearchTool,
    telemetry_sink: TelemetrySink | None = None,
) -> Callable[[str], Any]:
    
    async def web_search(query: str) -> str:
        """Search the web for current information and recent facts."""
        started = time.monotonic()
        try:
            results = await search_tool.search(query=query, max_results=5)
            lines: list[str] = []
            for item in results:
                title = item.title or "(untitled)"
                url = item.url or "(no-url)"
                snippet = item.snippet or ""
                lines.append(f"- {title} | {url} | {snippet}")
            output_text = "\n".join(lines) if lines else "- No search results returned."
            _emit_telemetry(
                telemetry_sink,
                ToolInvocationTelemetry(
                    tool_name="search",
                    input_json=json.dumps({"query": query}),
                    output_json=json.dumps({"result_count": len(results)}),
                    status="success",
                    latency_ms=int((time.monotonic() - started) * 1000),
                ),
            )
            return output_text
        except Exception as exc:
            _emit_telemetry(
                telemetry_sink,
                ToolInvocationTelemetry(
                    tool_name="search",
                    input_json=json.dumps({"query": query}),
                    output_json=json.dumps({"error": str(exc)}),
                    status="error",
                    latency_ms=int((time.monotonic() - started) * 1000),
                ),
            )
            return f"Search failed: {exc}"

    return web_search


def make_read_file_tool_execute(
    *,
    room_id: str | None,
    session_id: str | None = None,
    db: AsyncSession,
    file_tool: FileReadTool,
    telemetry_sink: TelemetrySink | None = None,
) -> Callable[[str], Any]:

    async def read_file(file_id: str) -> str:
        """Read an uploaded file by file id and return parsed content."""
        started = time.monotonic()
        if room_id is None and session_id is None:
            _emit_telemetry(
                telemetry_sink,
                ToolInvocationTelemetry(
                    tool_name="file_read",
                    input_json=json.dumps({"file_id": file_id}),
                    output_json=json.dumps({"error": "file_read requires either a room_id or session_id"}),
                    status="error",
                    latency_ms=int((time.monotonic() - started) * 1000),
                ),
            )
            return "File read is unavailable without an active room or session scoped context."

        try:
            result = await file_tool.read(file_id=file_id, room_id=room_id, session_id=session_id, db=db)
            if result.status == "completed":
                content = result.content or ""
                _emit_telemetry(
                    telemetry_sink,
                    ToolInvocationTelemetry(
                        tool_name="file_read",
                        input_json=json.dumps({"file_id": file_id}),
                        output_json=json.dumps({"chars": len(content)}),
                        status="success",
                        latency_ms=int((time.monotonic() - started) * 1000),
                    ),
                )
                return content

            message = result.error or "File read failed."
            _emit_telemetry(
                telemetry_sink,
                ToolInvocationTelemetry(
                    tool_name="file_read",
                    input_json=json.dumps({"file_id": file_id}),
                    output_json=json.dumps({"error": message, "result_status": result.status}),
                    status="error",
                    latency_ms=int((time.monotonic() - started) * 1000),
                ),
            )
            return message
        except Exception as exc:
            _emit_telemetry(
                telemetry_sink,
                ToolInvocationTelemetry(
                    tool_name="file_read",
                    input_json=json.dumps({"file_id": file_id}),
                    output_json=json.dumps({"error": str(exc)}),
                    status="error",
                    latency_ms=int((time.monotonic() - started) * 1000),
                ),
            )
            return f"File read failed: {exc}"

    return read_file
