"""Pydantic models for structured LLM output.

The LLM is forced to return JSON conforming to these schemas via
OpenAI's Structured Outputs feature (response_format).  This guarantees
clean, parseable responses and eliminates prompt-based formatting hacks.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class AgentResponse(BaseModel):
    """The structured response every agent must return.

    Fields
    ------
    thinking : str
        Internal chain-of-thought reasoning.  This is the agent's private
        scratchpad — it is logged for debugging but **never** shown to end
        users in the chat.  The agent should use this to plan its answer,
        consider context, and organise thoughts before writing ``response``.
        Can be left empty (``""``).

        *Example*: ``"The user asked about AI products. I should suggest
        something innovative that aligns with Google's strengths."``

    response : str
        The actual content that will be displayed in the chat and stored
        in the conversation history.  This must be the agent's **direct
        speech only** — no name tags, no bracketed prefixes, no dialogue
        attributed to other participants.  Markdown is allowed.

        *Example*: ``"I'd propose an AI-powered research assistant that
        can synthesise academic papers in real-time."``
    """

    thinking: str = Field(
        default="",
        description=(
            "Internal reasoning / chain-of-thought. "
            "NOT shown to users; used for planning and debugging only."
        ),
    )
    response: str = Field(
        ...,
        description=(
            "The agent's direct speech to display in chat. "
            "Must NOT contain name tags, bracketed prefixes, or dialogue for other agents."
        ),
    )
