import asyncio
from dataclasses import dataclass
import sys
import os

# Add root to sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from apps.api.app.services.llm.gateway import OpenAICompatibleGateway
from apps.api.app.services.orchestration.orchestrator_manager import route_turn
from apps.api.app.core.config import get_settings

@dataclass
class MockAgent:
    name: str
    agent_key: str
    role_prompt: str
    tool_permissions: list[str]

async def main():
    agents = [
        MockAgent("Elon", "elon", "You are Elon Musk. You are the CEO of Tesla and SpaceX. You are focused on physics and first principles.", []),
        MockAgent("Sundar", "sundar", "You are Sundar Pichai. You are the CEO of Google. You are thoughtful, measured, and focused on organizing the world's information.", []),
        MockAgent("Sam", "sam", "You are Sam Altman. You are the CEO of OpenAI. You are focused on AGI and iterative deployment.", [])
    ]
    
    settings = get_settings()
    gateway = OpenAICompatibleGateway()
    manager_alias = settings.orchestrator_manager_model_alias
    
    print(f"Manager model alias: {manager_alias}")
    
    user_input = "I want all CEOs to review each others critiques in managing style, and then present all results to me"
    print(f"\nTesting with input: {user_input}")
    
    decision = await route_turn(
        agents=agents,
        user_input=user_input,
        gateway=gateway,
        manager_model_alias=manager_alias
    )
    print(f"Decision 1: {decision.selected_agent_keys}")
    
    user_input_2 = "What does Elon think about Mars?"
    print(f"\nTesting with input: {user_input_2}")
    decision2 = await route_turn(
        agents=agents,
        user_input=user_input_2,
        gateway=gateway,
        manager_model_alias=manager_alias
    )
    print(f"Decision 2: {decision2.selected_agent_keys}")

    user_input_3 = "Now let Sundar respond to Elon."
    print(f"\nTesting with input: {user_input_3} (with prior outputs)")
    decision3 = await route_turn(
        agents=agents,
        user_input=user_input_3,
        gateway=gateway,
        manager_model_alias=manager_alias,
        prior_round_outputs=[("Elon", "We must go to Mars!")]
    )
    print(f"Decision 3: {decision3.selected_agent_keys}")
    
if __name__ == "__main__":
    asyncio.run(main())
