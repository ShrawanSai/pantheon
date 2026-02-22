from __future__ import annotations

import unittest

from apps.api.app.db.models import RoomAgent
from apps.api.app.services.tools.permissions import get_permitted_tool_names, is_tool_permitted


class ToolPermissionTests(unittest.TestCase):
    def test_get_permitted_and_allowed_when_search_present(self) -> None:
        agent = RoomAgent(tool_permissions_json='["search"]')
        self.assertEqual(get_permitted_tool_names(agent), ["search"])
        self.assertTrue(is_tool_permitted(agent, "search"))

    def test_not_permitted_when_only_file_read_present(self) -> None:
        agent = RoomAgent(tool_permissions_json='["file_read"]')
        self.assertEqual(get_permitted_tool_names(agent), ["file_read"])
        self.assertFalse(is_tool_permitted(agent, "search"))

    def test_empty_permissions(self) -> None:
        agent = RoomAgent(tool_permissions_json="[]")
        self.assertEqual(get_permitted_tool_names(agent), [])
        self.assertFalse(is_tool_permitted(agent, "search"))

    def test_multi_tool_permissions(self) -> None:
        agent = RoomAgent(tool_permissions_json='["search","file_read"]')
        self.assertEqual(get_permitted_tool_names(agent), ["search", "file_read"])
        self.assertTrue(is_tool_permitted(agent, "search"))

    def test_malformed_permissions_fallback_to_empty(self) -> None:
        agent = RoomAgent(tool_permissions_json="not json")
        self.assertEqual(get_permitted_tool_names(agent), [])
        self.assertFalse(is_tool_permitted(agent, "search"))


if __name__ == "__main__":
    unittest.main()

