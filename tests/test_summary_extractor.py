from __future__ import annotations

import asyncio
from dataclasses import dataclass
import unittest
from unittest.mock import patch

from apps.api.app.services.llm.gateway import GatewayRequest, GatewayResponse, GatewayUsage
from apps.api.app.services.orchestration.summary_extractor import (
    SummaryStructure,
    extract_summary_structure,
)


@dataclass
class FakeGateway:
    response_text: str

    async def generate(self, request: GatewayRequest) -> GatewayResponse:
        _ = request
        return GatewayResponse(
            text=self.response_text,
            provider_model="fake/summary-model",
            usage=GatewayUsage(
                input_tokens_fresh=1,
                input_tokens_cached=0,
                output_tokens=1,
                total_tokens=2,
            ),
        )


class SummaryExtractorTests(unittest.TestCase):
    def test_extract_returns_structured_content_from_valid_json(self) -> None:
        gateway = FakeGateway(
            response_text="""
            {
              "key_facts": ["fact a", "fact b"],
              "decisions": ["decision a"],
              "open_questions": ["question a"],
              "action_items": ["action a"]
            }
            """
        )

        async def run() -> SummaryStructure:
            return await extract_summary_structure(
                summary_text="A summary text",
                gateway=gateway,
                model_alias="deepseek",
            )

        structure = asyncio.run(run())
        self.assertEqual(structure.key_facts, ["fact a", "fact b"])
        self.assertEqual(structure.decisions, ["decision a"])
        self.assertEqual(structure.open_questions, ["question a"])
        self.assertEqual(structure.action_items, ["action a"])

    def test_extract_falls_back_to_empty_on_invalid_json(self) -> None:
        gateway = FakeGateway(response_text="not json")

        async def run() -> SummaryStructure:
            return await extract_summary_structure(
                summary_text="A summary text",
                gateway=gateway,
                model_alias="deepseek",
            )

        with patch("apps.api.app.services.orchestration.summary_extractor._LOGGER") as logger:
            structure = asyncio.run(run())
        self.assertEqual(structure, SummaryStructure([], [], [], []))
        logger.warning.assert_called()

    def test_extract_defaults_missing_keys_without_fallback_warning(self) -> None:
        gateway = FakeGateway(response_text='{"key_facts":["x"]}')

        async def run() -> SummaryStructure:
            return await extract_summary_structure(
                summary_text="A summary text",
                gateway=gateway,
                model_alias="deepseek",
            )

        with patch("apps.api.app.services.orchestration.summary_extractor._LOGGER") as logger:
            structure = asyncio.run(run())
        self.assertEqual(structure.key_facts, ["x"])
        self.assertEqual(structure.decisions, [])
        self.assertEqual(structure.open_questions, [])
        self.assertEqual(structure.action_items, [])
        logger.warning.assert_not_called()


if __name__ == "__main__":
    unittest.main()
