from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from uuid import uuid4
import unittest
from unittest.mock import patch

from apps.api.app.services.orchestration.mode_executor import ActiveAgent
from apps.api.app.services.llm.gateway import GatewayRequest, GatewayResponse, GatewayUsage
from apps.api.app.services.orchestration.orchestrator_manager import (
    OrchestratorRoundDecision,
    evaluate_orchestrator_round,
    route_turn,
    _strip_json_fences,
)


@dataclass
class FakeGateway:
    response_text: str
    calls: list[GatewayRequest] = field(default_factory=list)

    async def generate(self, request: GatewayRequest) -> GatewayResponse:
        self.calls.append(request)
        return GatewayResponse(
            text=self.response_text,
            provider_model="fake/router",
            usage=GatewayUsage(
                input_tokens_fresh=1,
                input_tokens_cached=0,
                output_tokens=1,
                total_tokens=2,
            ),
        )


def _agent(key: str, role_prompt: str, model_alias: str = "deepseek", position: int = 1) -> ActiveAgent:
    _ = position
    return ActiveAgent(
        agent_id=str(uuid4()),
        agent_key=key,
        name=key.title(),
        model_alias=model_alias,
        role_prompt=role_prompt,
        tool_permissions=(),
    )


class OrchestratorManagerTests(unittest.TestCase):
    def test_route_turn_selects_agent_sequence_from_valid_json_response(self) -> None:
        gateway = FakeGateway(response_text='{"selected_agent_keys":["researcher","writer"]}')
        agents = [
            _agent("writer", "Writes polished output."),
            _agent("researcher", "Finds supporting evidence."),
        ]

        async def run():
            return await route_turn(
                agents=agents,
                user_input="Need factual support.",
                gateway=gateway,
                manager_model_alias="deepseek",
            )

        decision = asyncio.run(run())
        self.assertEqual(decision.selected_agent_keys, ("researcher", "writer"))
        self.assertEqual(decision.selected_agent_key, "researcher")

    def test_route_turn_accepts_legacy_single_key_contract(self) -> None:
        gateway = FakeGateway(response_text='{"selected_agent_key":"researcher"}')
        agents = [
            _agent("writer", "Writes polished output."),
            _agent("researcher", "Finds supporting evidence."),
        ]

        async def run():
            return await route_turn(
                agents=agents,
                user_input="Need factual support.",
                gateway=gateway,
                manager_model_alias="deepseek",
            )

        decision = asyncio.run(run())
        self.assertEqual(decision.selected_agent_keys, ("researcher",))

    def test_route_turn_falls_back_to_first_agent_on_invalid_json(self) -> None:
        gateway = FakeGateway(response_text="not json at all")
        agents = [
            _agent("writer", "Writes polished output."),
            _agent("researcher", "Finds supporting evidence."),
        ]

        async def run():
            return await route_turn(
                agents=agents,
                user_input="Need factual support.",
                gateway=gateway,
                manager_model_alias="deepseek",
            )

        with patch("apps.api.app.services.orchestration.orchestrator_manager._LOGGER") as logger:
            decision = asyncio.run(run())
        self.assertEqual(decision.selected_agent_key, "writer")
        logger.warning.assert_called()

    def test_route_turn_falls_back_to_first_agent_on_unknown_key(self) -> None:
        gateway = FakeGateway(response_text='{"selected_agent_keys":["ghost"]}')
        agents = [
            _agent("writer", "Writes polished output."),
            _agent("researcher", "Finds supporting evidence."),
        ]

        async def run():
            return await route_turn(
                agents=agents,
                user_input="Need factual support.",
                gateway=gateway,
                manager_model_alias="deepseek",
            )

        with patch("apps.api.app.services.orchestration.orchestrator_manager._LOGGER") as logger:
            decision = asyncio.run(run())
        self.assertEqual(decision.selected_agent_key, "writer")
        logger.warning.assert_called()


class StripJsonFencesTests(unittest.TestCase):
    def test_strips_json_fences(self) -> None:
        fenced = '```json\n{"continue": false}\n```'
        self.assertEqual(_strip_json_fences(fenced), '{"continue": false}')

    def test_strips_plain_fences(self) -> None:
        fenced = '```\n{"continue": true}\n```'
        self.assertEqual(_strip_json_fences(fenced), '{"continue": true}')

    def test_passthrough_when_no_fences(self) -> None:
        raw = '{"continue": false}'
        self.assertEqual(_strip_json_fences(raw), raw)

    def test_strips_fences_with_surrounding_prose(self) -> None:
        # DeepSeek-style: JSON fence followed by prose
        fenced = '```json\n{"continue": false}\n```\n\nSome explanation here.'
        self.assertEqual(_strip_json_fences(fenced), '{"continue": false}')


class EvaluateOrchestratorRoundFenceTests(unittest.TestCase):
    def test_evaluate_round_parses_fenced_json(self) -> None:
        gateway = FakeGateway(response_text='```json\n{"continue": true}\n```')

        async def run():
            return await evaluate_orchestrator_round(
                gateway=gateway,
                manager_model_alias="deepseek",
                user_input="Keep going?",
                all_round_outputs=[("writer", "Some output.")],
                current_round=1,
            )

        decision = asyncio.run(run())
        self.assertTrue(decision.should_continue)

    def test_route_turn_parses_fenced_routing_json(self) -> None:
        gateway = FakeGateway(
            response_text='```json\n{"selected_agent_keys":["researcher"]}\n```'
        )
        agents = [
            _agent("writer", "Writes polished output."),
            _agent("researcher", "Finds supporting evidence."),
        ]

        async def run():
            return await route_turn(
                agents=agents,
                user_input="Need factual support.",
                gateway=gateway,
                manager_model_alias="deepseek",
            )

        decision = asyncio.run(run())
        self.assertEqual(decision.selected_agent_key, "researcher")


if __name__ == "__main__":
    unittest.main()
