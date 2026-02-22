from __future__ import annotations

import json

from apps.api.app.db.models import RoomAgent


def get_permitted_tool_names(agent: RoomAgent) -> list[str]:
    """Return canonical tool names an agent is allowed to invoke."""
    raw = agent.tool_permissions_json or "[]"
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []

    tools: list[str] = []
    for item in parsed:
        if not isinstance(item, str):
            continue
        normalized = item.strip().lower()
        if normalized:
            tools.append(normalized)
    return tools


def is_tool_permitted(agent: RoomAgent, tool_name: str) -> bool:
    """Return True if tool_name is present in the agent's allowed tool list."""
    normalized = tool_name.strip().lower()
    if not normalized:
        return False
    return normalized in get_permitted_tool_names(agent)

