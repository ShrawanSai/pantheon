from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor
from typing import Literal, Sequence


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

        base_messages: list[ContextMessage] = list(system_messages)
        if latest_summary_text:
            base_messages.append(ContextMessage(role="system", content=f"Session summary: {latest_summary_text}"))

        raw_history_messages = [ContextMessage(role=item.role, content=item.content) for item in history_messages]
        before_messages = [*base_messages, *raw_history_messages, ContextMessage(role="user", content=user_input)]
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

        final_history_messages = [ContextMessage(role=item.role, content=item.content) for item in working_history]
        final_messages = [*base_messages, *final_history_messages, ContextMessage(role="user", content=user_input)]

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
