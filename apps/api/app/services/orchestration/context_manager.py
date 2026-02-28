from __future__ import annotations

import json
import re
from dataclasses import dataclass
from math import ceil, floor
from typing import TYPE_CHECKING, Any, Literal, Protocol, Sequence

if TYPE_CHECKING:
    from datetime import datetime


ContextRole = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class ContextMessage:
    role: ContextRole
    content: str


@dataclass(frozen=True)
class HistoryMessage:
    id: str
    role: ContextRole
    content: str
    turn_id: str | None


@dataclass(frozen=True)
class ContextPreparation:
    messages: list[ContextMessage]
    model_context_limit: int
    input_budget: int
    output_reserve: int
    overhead_reserve: int
    estimated_input_tokens_before: int
    estimated_input_tokens_after_summary: int
    estimated_input_tokens_after_prune: int
    summary_triggered: bool
    prune_triggered: bool
    overflow_rejected: bool
    generated_summary_text: str | None
    summary_from_message_id: str | None
    summary_to_message_id: str | None


@dataclass(frozen=True)
class ContextBudgetExceeded(Exception):
    model_context_limit: int
    input_budget: int
    estimated_tokens: int


class MessageRow(Protocol):
    """Structural protocol matching db.models.Message columns used by history building."""
    id: str
    turn_id: str | None
    role: str
    visibility: str
    agent_key: str | None
    source_agent_key: str | None
    agent_name: str | None
    content: str
    created_at: datetime


class ToolCallRow(Protocol):
    """Structural protocol matching db.models.ToolCallEvent columns used by tool memory."""
    tool_name: str
    tool_input_json: str
    tool_output_json: str
    status: str
    created_at: datetime


_NAME_TAG_BRACKET = re.compile(r'^\[.*?\]:\s*')
_NAME_TAG_PREFIX = re.compile(r'^[A-Za-z0-9_\s]{2,20}:\s*')


def build_history_messages(
    history_rows: Sequence[MessageRow],
    *,
    is_room: bool,
    current_agent_key: str | None = None,
    agent_private_turns_keep: int = 3,
) -> list[HistoryMessage]:
    """Build a unified HistoryMessage list from DB message rows.

    When *current_agent_key* is supplied (multi-agent modes), private messages
    belonging to that agent are merged into the timeline (limited to the most
    recent *agent_private_turns_keep* pairs).  Otherwise only shared messages
    are included.
    """
    if is_room and current_agent_key is not None:
        shared = [r for r in history_rows if r.visibility == "shared"]
        private = [
            r for r in history_rows
            if r.visibility == "private" and r.agent_key == current_agent_key
        ]
        private_limit = max(agent_private_turns_keep, 0) * 2
        if private_limit > 0 and len(private) > private_limit:
            private = private[-private_limit:]
        combined: list[MessageRow] = sorted(
            [*shared, *private], key=lambda r: (r.created_at, r.id)
        )
    elif is_room:
        combined = sorted(history_rows, key=lambda r: (r.created_at, r.id))
    else:
        combined = [r for r in history_rows if r.visibility == "shared"]

    output: list[HistoryMessage] = []
    for msg in combined:
        if msg.role not in {"user", "assistant", "tool"}:
            continue
        role: ContextRole = "user" if msg.role == "user" else "assistant"
        content = msg.content

        if msg.role == "assistant":
            content = _NAME_TAG_BRACKET.sub("", content)
            content = _NAME_TAG_PREFIX.sub("", content)

        if (
            is_room
            and msg.role == "assistant"
            and msg.visibility == "shared"
            and current_agent_key is not None
            and msg.source_agent_key is not None
            and msg.source_agent_key != current_agent_key
        ):
            content = f"[{msg.agent_name or msg.source_agent_key}]: {content}"
        elif is_room and msg.role == "assistant" and msg.visibility == "shared":
            content = f"{msg.agent_name or msg.source_agent_key}: {content}"

        output.append(HistoryMessage(id=msg.id, role=role, content=content, turn_id=msg.turn_id))
    return output


def build_tool_memory_block(
    tool_events: Sequence[ToolCallRow],
    max_events: int = 10,
) -> str | None:
    """Build a compact text block summarising an agent's recent tool calls.

    Returns *None* when there are no events, so callers can skip the message.
    """
    if not tool_events:
        return None

    recent = list(tool_events)[-max_events:]
    lines: list[str] = []
    for evt in recent:
        try:
            args = json.loads(evt.tool_input_json)
            args_short = ", ".join(f"{k}={v!r}" for k, v in args.items())
        except (json.JSONDecodeError, AttributeError):
            args_short = evt.tool_input_json[:80]

        output_snippet = evt.tool_output_json[:200]
        if len(evt.tool_output_json) > 200:
            output_snippet += "..."
        lines.append(f"- {evt.tool_name}({args_short}) → {output_snippet}")

    return "You previously used these tools:\n" + "\n".join(lines)


class ContextManager:
    def __init__(
        self,
        *,
        max_output_tokens: int,
        summary_trigger_ratio: float,
        prune_trigger_ratio: float,
        mandatory_summary_turn: int,
        recent_turns_to_keep: int,
    ) -> None:
        self.max_output_tokens = max(max_output_tokens, 256)
        self.summary_trigger_ratio = min(max(summary_trigger_ratio, 0.1), 1.0)
        self.prune_trigger_ratio = min(max(prune_trigger_ratio, self.summary_trigger_ratio), 1.0)
        self.mandatory_summary_turn = max(mandatory_summary_turn, 1)
        self.recent_turns_to_keep = max(recent_turns_to_keep, 1)

    @staticmethod
    def estimate_tokens_text(text: str) -> int:
        return max(1, ceil(len(text) / 4 * 1.25))

    def estimate_tokens(self, messages: Sequence[ContextMessage]) -> int:
        return sum(self.estimate_tokens_text(message.content) for message in messages)

    def prepare(
        self,
        *,
        model_context_limit: int,
        system_messages: Sequence[ContextMessage],
        history_messages: Sequence[HistoryMessage],
        latest_summary_text: str | None,
        turn_count_since_last_summary: int,
        user_input: str,
    ) -> ContextPreparation:
        model_limit = max(model_context_limit, 2048)
        output_reserve = min(self.max_output_tokens, floor(model_limit * 0.20))
        overhead_reserve = max(1024, floor(model_limit * 0.05))
        input_budget = model_limit - output_reserve - overhead_reserve
        if input_budget <= 0:
            raise ContextBudgetExceeded(
                model_context_limit=model_limit,
                input_budget=input_budget,
                estimated_tokens=0,
            )

        base_messages: list[ContextMessage] = [ContextMessage(role="system", content="--- SYSTEM ---")]
        base_messages.extend(list(system_messages))
        if latest_summary_text:
            base_messages.append(ContextMessage(role="system", content=f"Session summary: {latest_summary_text}"))

        raw_history_messages = [ContextMessage(role=item.role, content=item.content) for item in history_messages]
        if raw_history_messages:
            history_block = [ContextMessage(role="system", content="--- HISTORY ---"), *raw_history_messages]
        else:
            history_block = []

        before_messages = [
            *base_messages,
            *history_block,
            ContextMessage(role="system", content="--- CURRENT TURN ---"),
            ContextMessage(role="user", content=user_input)
        ]
        estimated_before = self.estimate_tokens(before_messages)

        summary_triggered = False
        prune_triggered = False
        summary_from_message_id: str | None = None
        summary_to_message_id: str | None = None

        working_history = list(history_messages)

        should_summarize = (
            estimated_before >= int(input_budget * self.summary_trigger_ratio)
            or turn_count_since_last_summary >= self.mandatory_summary_turn
        )

        if should_summarize:
            summarize_cutoff = max(len(working_history) - (self.recent_turns_to_keep * 2), 0)
            summarizable = working_history[:summarize_cutoff]
            if summarizable:
                summary_triggered = True
                summary_from_message_id = summarizable[0].id
                summary_to_message_id = summarizable[-1].id
                working_history = working_history[summarize_cutoff:]

        current_history_messages = [ContextMessage(role=item.role, content=item.content) for item in working_history]
        current_messages = [*base_messages, *current_history_messages, ContextMessage(role="user", content=user_input)]
        estimated_after_summary = self.estimate_tokens(current_messages)

        if estimated_after_summary >= int(input_budget * self.prune_trigger_ratio):
            prune_triggered = True
            while working_history:
                working_history.pop(0)
                current_history_messages = [ContextMessage(role=item.role, content=item.content) for item in working_history]
                current_messages = [*base_messages, *current_history_messages, ContextMessage(role="user", content=user_input)]
                if self.estimate_tokens(current_messages) <= input_budget:
                    break
            
            estimated_after_prune = self.estimate_tokens(current_messages)
            if estimated_after_prune > input_budget:
                raise ContextBudgetExceeded(
                    model_context_limit=model_limit,
                    input_budget=input_budget,
                    estimated_tokens=estimated_after_prune,
                )
        else:
            estimated_after_prune = estimated_after_summary

        if working_history:
            final_history_messages = [ContextMessage(role="system", content="--- HISTORY ---")]
            final_history_messages.extend([ContextMessage(role=item.role, content=item.content) for item in working_history])
        else:
            final_history_messages = []

        final_messages = [
            *base_messages,
            *final_history_messages,
            ContextMessage(role="system", content="--- CURRENT TURN ---"),
            ContextMessage(role="user", content=user_input)
        ]

        return ContextPreparation(
            messages=final_messages,
            model_context_limit=model_limit,
            input_budget=input_budget,
            output_reserve=output_reserve,
            overhead_reserve=overhead_reserve,
            estimated_input_tokens_before=estimated_before,
            estimated_input_tokens_after_summary=estimated_after_summary,
            estimated_input_tokens_after_prune=estimated_after_prune,
            summary_triggered=summary_triggered,
            prune_triggered=prune_triggered,
            overflow_rejected=False,
            generated_summary_text=None,
            summary_from_message_id=summary_from_message_id,
            summary_to_message_id=summary_to_message_id,
        )
