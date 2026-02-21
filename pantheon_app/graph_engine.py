from __future__ import annotations

import re
from typing import Any, AsyncIterator, Literal, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from pantheon_llm.openrouter_langchain import ainvoke_messages


class Agent(TypedDict):
    id: str
    name: str
    model_alias: str
    role_prompt: str


class ModeState(TypedDict, total=False):
    mode: Literal["manual", "roundtable", "orchestrator"]
    user_input: str
    tagged_agents: list[str]
    history_text: str
    manager_alias: str
    agents: list[Agent]
    steps: list[dict[str, str]]
    assistant_output: str
    error: str


DEFAULT_AGENTS: list[Agent] = [
    {
        "id": "researcher",
        "name": "Research Analyst",
        "model_alias": "deepseek",
        "role_prompt": "You extract facts and key points. Keep output concise and structured.",
    },
    {
        "id": "writer",
        "name": "Writer",
        "model_alias": "gpt_oss",
        "role_prompt": "You draft clear and polished responses from prior context.",
    },
    {
        "id": "reviewer",
        "name": "Reviewer",
        "model_alias": "qwen",
        "role_prompt": "You quality-check outputs and provide a final recommendation.",
    },
]


def _trim(text: str, max_chars: int = 900) -> str:
    t = text.strip()
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 3] + "..."


def _parse_tagged_agents(user_input: str, available: list[Agent]) -> list[str]:
    tags = [m.group(1).lower() for m in re.finditer(r"@([a-zA-Z0-9_\\-]+)", user_input)]
    if not tags:
        return []
    valid = {a["id"].lower() for a in available} | {a["name"].lower().replace(" ", "") for a in available}
    resolved: list[str] = []
    for tag in tags:
        if tag in valid:
            for a in available:
                if tag == a["id"].lower() or tag == a["name"].lower().replace(" ", ""):
                    resolved.append(a["id"])
                    break
    deduped: list[str] = []
    for agent_id in resolved:
        if agent_id not in deduped:
            deduped.append(agent_id)
    return deduped


def _roster_summary(roster: list[Agent]) -> str:
    lines = []
    for a in roster:
        lines.append(f"- id={a['id']} | name={a['name']} | model={a['model_alias']} | role={a['role_prompt']}")
    return "\n".join(lines)


async def _run_agent_with_roster(
    agent: Agent,
    user_input: str,
    history_text: str,
    mode: str,
    prior_steps: list[dict[str, str]],
    roster: list[Agent],
    allow_agent_interaction: bool = False,
) -> str:
    interaction_rule = (
        "You may reference and build on prior agent outputs when relevant."
        if allow_agent_interaction
        else (
            "Do not address, instruct, critique, or mention other agents. "
            "Provide only your own role-based response to the user."
        )
    )
    messages = [
        SystemMessage(
            content=(
                f"You are '{agent['name']}'. {agent['role_prompt']}\n"
                "Always provide concise, actionable output.\n"
                f"{interaction_rule}"
            )
        ),
        SystemMessage(
            content=(
                "You are part of a multi-agent room. Be aware of the other agents in the room.\n"
                f"Current room roster:\n{_roster_summary(roster)}"
            )
        ),
        HumanMessage(content=f"Conversation mode: {mode}"),
        HumanMessage(content=f"Conversation history:\n{_trim(history_text, 1800)}"),
    ]
    if prior_steps:
        messages.append(
            HumanMessage(
                content=(
                    "Context from earlier agent outputs is provided below. "
                    "Use only as background context."
                )
            )
        )
        for step in prior_steps:
            messages.append(
                AIMessage(content=f"{step['agent_name']}: {_trim(step['output_text'], 320)}")
            )
    messages.append(HumanMessage(content=f"User request:\n{user_input}"))
    return await ainvoke_messages(agent["model_alias"], messages)


class ChatGraphEngine:
    def __init__(self) -> None:
        self._graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(ModeState)
        graph.add_node("route", self._route_node)
        graph.add_node("manual", self._manual_node)
        graph.add_node("roundtable", self._roundtable_node)
        graph.add_node("orchestrator", self._orchestrator_node)
        graph.add_node("error", self._error_node)

        graph.add_edge(START, "route")
        graph.add_conditional_edges(
            "route",
            self._route_edge,
            {
                "manual": "manual",
                "roundtable": "roundtable",
                "orchestrator": "orchestrator",
                "error": "error",
            },
        )
        graph.add_edge("manual", END)
        graph.add_edge("roundtable", END)
        graph.add_edge("orchestrator", END)
        graph.add_edge("error", END)
        return graph.compile()

    async def run_turn(
        self,
        mode: str,
        user_input: str,
        history_text: str,
        manager_alias: str = "deepseek",
        tagged_agents: list[str] | None = None,
        agents: list[Agent] | None = None,
    ) -> dict[str, Any]:
        init_state: ModeState = {
            "mode": mode,  # type: ignore[assignment]
            "user_input": user_input,
            "history_text": history_text,
            "manager_alias": manager_alias,
            "tagged_agents": tagged_agents or [],
            "agents": agents or DEFAULT_AGENTS,
            "steps": [],
            "assistant_output": "",
            "error": "",
        }
        result = await self._graph.ainvoke(init_state)
        return result

    async def stream_turn(
        self,
        mode: str,
        user_input: str,
        history_text: str,
        manager_alias: str = "deepseek",
        tagged_agents: list[str] | None = None,
        agents: list[Agent] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        roster = agents or DEFAULT_AGENTS
        tags = tagged_agents or []
        by_id = {a["id"]: a for a in roster}

        if mode == "manual":
            resolved = tags or _parse_tagged_agents(user_input, roster)
            if not resolved:
                yield {"type": "error", "error": "Manual/tag mode requires at least one tagged agent, e.g. @researcher"}
                return
            steps: list[dict[str, str]] = []
            for tag in resolved:
                agent = by_id.get(tag)
                if not agent:
                    continue
                out = await _run_agent_with_roster(
                    agent, user_input, history_text, "manual", steps, roster, allow_agent_interaction=False
                )
                step = {"agent_name": agent["name"], "model_alias": agent["model_alias"], "output_text": out}
                steps.append(step)
                yield {"type": "step", "mode": mode, "step": step}
            if not steps:
                yield {"type": "error", "error": "No valid tagged agents were found in this room."}
                return
            yield {"type": "done", "mode": mode, "assistant_output": "\n\n".join([f"{s['agent_name']}: {s['output_text']}" for s in steps]), "steps": steps}
            return

        if mode == "roundtable":
            steps: list[dict[str, str]] = []
            for agent in roster:
                out = await _run_agent_with_roster(
                    agent, user_input, history_text, "roundtable", steps, roster, allow_agent_interaction=False
                )
                step = {"agent_name": agent["name"], "model_alias": agent["model_alias"], "output_text": out}
                steps.append(step)
                yield {"type": "step", "mode": mode, "step": step}
            yield {"type": "done", "mode": mode, "assistant_output": "\n\n".join([f"{s['agent_name']}: {s['output_text']}" for s in steps]), "steps": steps}
            return

        if mode == "orchestrator":
            routing_messages = [
                SystemMessage(
                    content=(
                        "You are an orchestration manager. "
                        "Select which specialist agents should run and in what order."
                    )
                ),
                HumanMessage(content=f"Available agent IDs: {', '.join(by_id.keys())}"),
                HumanMessage(content=f"User message: {user_input}"),
                HumanMessage(content="Return only comma-separated agent IDs in execution order."),
            ]
            manager_out = await ainvoke_messages(manager_alias, routing_messages)
            routed = [x.strip().lower() for x in manager_out.split(",") if x.strip()]
            selected = [a for a in routed if a in by_id] or ["researcher", "writer", "reviewer"]

            steps: list[dict[str, str]] = []
            for agent_id in selected[:3]:
                agent = by_id[agent_id]
                out = await _run_agent_with_roster(
                    agent, user_input, history_text, "orchestrator", steps, roster, allow_agent_interaction=False
                )
                step = {"agent_name": agent["name"], "model_alias": agent["model_alias"], "output_text": out}
                steps.append(step)
                yield {"type": "step", "mode": mode, "step": step}

            synthesis_messages = [
                SystemMessage(
                    content=(
                        "You are the final synthesizer. Combine specialist outputs into a coherent final response."
                    )
                ),
                HumanMessage(content=f"Original user message: {user_input}"),
                HumanMessage(content="Specialist outputs are provided below."),
            ]
            for step in steps:
                synthesis_messages.append(AIMessage(content=f"{step['agent_name']}: {_trim(step['output_text'], 420)}"))
            synthesis_messages.append(HumanMessage(content="Return the final answer only."))
            final = await ainvoke_messages(manager_alias, synthesis_messages)
            final_step = {"agent_name": "Orchestrator Final", "model_alias": manager_alias, "output_text": final}
            steps.append(final_step)
            yield {"type": "step", "mode": mode, "step": final_step}
            yield {"type": "done", "mode": mode, "assistant_output": final, "steps": steps}
            return

        yield {"type": "error", "error": f"Unsupported mode: {mode}"}

    async def _route_node(self, state: ModeState) -> ModeState:
        mode = state.get("mode")
        if mode not in {"manual", "roundtable", "orchestrator"}:
            return {"error": f"Unsupported mode: {mode}"}
        return state

    def _route_edge(self, state: ModeState) -> str:
        if state.get("error"):
            return "error"
        return str(state.get("mode"))

    async def _manual_node(self, state: ModeState) -> ModeState:
        agents = state.get("agents", [])
        tags = state.get("tagged_agents") or _parse_tagged_agents(state["user_input"], agents)
        if not tags:
            return {"error": "Manual/tag mode requires at least one tagged agent, e.g. @researcher"}

        by_id = {a["id"]: a for a in agents}
        steps: list[dict[str, str]] = []
        for tag in tags:
            agent = by_id.get(tag)
            if not agent:
                continue
            out = await _run_agent_with_roster(
                agent,
                state["user_input"],
                state["history_text"],
                "manual",
                steps,
                agents,
                allow_agent_interaction=False,
            )
            steps.append(
                {
                    "agent_name": agent["name"],
                    "model_alias": agent["model_alias"],
                    "output_text": out,
                }
            )
        if not steps:
            return {"error": "No valid tagged agents were found in this room."}
        final_text = "\n\n".join([f"{s['agent_name']}: {s['output_text']}" for s in steps])
        return {"steps": steps, "assistant_output": final_text}

    async def _roundtable_node(self, state: ModeState) -> ModeState:
        steps: list[dict[str, str]] = []
        for agent in state.get("agents", []):
            out = await _run_agent_with_roster(
                agent,
                state["user_input"],
                state["history_text"],
                "roundtable",
                steps,
                state.get("agents", []),
                allow_agent_interaction=False,
            )
            steps.append(
                {
                    "agent_name": agent["name"],
                    "model_alias": agent["model_alias"],
                    "output_text": out,
                }
            )
        final_text = "\n\n".join([f"{s['agent_name']}: {s['output_text']}" for s in steps])
        return {"steps": steps, "assistant_output": final_text}

    async def _orchestrator_node(self, state: ModeState) -> ModeState:
        agents = state.get("agents", [])
        by_id = {a["id"]: a for a in agents}
        manager_alias = state.get("manager_alias", "deepseek")
        routing_messages = [
            SystemMessage(
                content=(
                    "You are an orchestration manager. "
                    "Select which specialist agents should run and in what order."
                )
            ),
            HumanMessage(content=f"Available agent IDs: {', '.join(by_id.keys())}"),
            HumanMessage(content=f"User message: {state['user_input']}"),
            HumanMessage(content="Return only comma-separated agent IDs in execution order."),
        ]
        manager_out = await ainvoke_messages(manager_alias, routing_messages)
        routed = [x.strip().lower() for x in manager_out.split(",") if x.strip()]
        selected = [a for a in routed if a in by_id]
        if not selected:
            selected = ["researcher", "writer", "reviewer"]

        steps: list[dict[str, str]] = []
        for agent_id in selected[:3]:
            agent = by_id[agent_id]
            out = await _run_agent_with_roster(
                agent,
                state["user_input"],
                state["history_text"],
                "orchestrator",
                steps,
                agents,
                allow_agent_interaction=False,
            )
            steps.append(
                {
                    "agent_name": agent["name"],
                    "model_alias": agent["model_alias"],
                    "output_text": out,
                }
            )
        synthesis_messages = [
            SystemMessage(
                content=(
                    "You are the final synthesizer. Combine specialist outputs into a coherent final response."
                )
            ),
            HumanMessage(content=f"Original user message: {state['user_input']}"),
            HumanMessage(content="Specialist outputs are provided below."),
        ]
        for step in steps:
            synthesis_messages.append(
                AIMessage(content=f"{step['agent_name']}: {_trim(step['output_text'], 420)}")
            )
        synthesis_messages.append(HumanMessage(content="Return the final answer only."))
        final = await ainvoke_messages(manager_alias, synthesis_messages)
        steps.append(
            {
                "agent_name": "Orchestrator Final",
                "model_alias": manager_alias,
                "output_text": final,
            }
        )
        return {"steps": steps, "assistant_output": final}

    async def _error_node(self, state: ModeState) -> ModeState:
        return state
