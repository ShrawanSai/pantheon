from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import unittest
from unittest.mock import patch

from apps.api.app.services.llm.gateway import GatewayRequest, GatewayResponse, GatewayUsage
from apps.api.app.services.orchestration.summary_generator import generate_summary_text


@dataclass
class FakeGateway:
    response_text: str
    calls: list[GatewayRequest] = field(default_factory=list)

    async def generate(self, request: GatewayRequest) -> GatewayResponse:
        self.calls.append(request)
        return GatewayResponse(
            text=self.response_text,
            provider_model="fake/summary-model",
            usage=GatewayUsage(
                input_tokens_fresh=10,
                input_tokens_cached=0,
                output_tokens=20,
                total_tokens=30,
            ),
        )


class SummaryGeneratorTests(unittest.TestCase):
    def test_generate_summary_text_returns_model_summary_on_valid_json(self) -> None:
        gateway = FakeGateway(response_text='{"summary_text":"Concise executive summary."}')

        async def run():
            return await generate_summary_text(
                raw_summary_text="Raw summary that should be rewritten.",
                gateway=gateway,
                model_alias="deepseek",
            )

        result = asyncio.run(run())
        self.assertFalse(result.used_fallback)
        self.assertEqual(result.summary_text, "Concise executive summary.")

    def test_generate_summary_text_falls_back_on_invalid_json(self) -> None:
        gateway = FakeGateway(response_text="not json")
        raw_summary = "Fallback source summary."

        async def run():
            return await generate_summary_text(
                raw_summary_text=raw_summary,
                gateway=gateway,
                model_alias="deepseek",
            )

        with patch("apps.api.app.services.orchestration.summary_generator._LOGGER") as logger:
            result = asyncio.run(run())
        self.assertTrue(result.used_fallback)
        self.assertEqual(result.summary_text, raw_summary)
        logger.warning.assert_called()

    def test_generate_summary_text_falls_back_on_missing_summary_text_key(self) -> None:
        gateway = FakeGateway(response_text='{"key_facts":["x"]}')
        raw_summary = "Fallback due to missing key."

        async def run():
            return await generate_summary_text(
                raw_summary_text=raw_summary,
                gateway=gateway,
                model_alias="deepseek",
            )

        with patch("apps.api.app.services.orchestration.summary_generator._LOGGER") as logger:
            result = asyncio.run(run())
        self.assertTrue(result.used_fallback)
        self.assertEqual(result.summary_text, raw_summary)
        logger.warning.assert_called()


if __name__ == "__main__":
    unittest.main()
