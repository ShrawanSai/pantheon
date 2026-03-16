"""Background job: auto-name a session based on the first user message."""
from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import select

from apps.api.app.db.session import get_session_factory
from apps.api.app.db.models import Session
from pantheon_llm.openrouter_langchain import ainvoke_text

_LOGGER = logging.getLogger(__name__)

_NAME_PROMPT = """\
Generate a session title for the task below. Rules:
- Maximum 4 words
- Noun phrase only (no verbs like "Can you", "Please", "How to")
- Describe the TOPIC, not the question
- No punctuation, no quotes
- Examples: "Drone Delivery Market", "Python API Design", "Climate Change Analysis"

Task:
{message}

Title:"""

_FILLER_WORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "can", "could", "would", "should", "will", "do", "does", "did",
    "i", "you", "we", "they", "he", "she", "it", "my", "your", "our",
    "please", "help", "me", "need", "want", "like", "get", "give", "tell",
    "what", "how", "why", "when", "where", "which", "who",
    "about", "for", "with", "on", "in", "at", "of", "to", "from",
})


def _clean_name(raw: str) -> str:
    """Strip quotes, trailing punctuation, and excessive whitespace."""
    name = raw.strip().strip('"\'').rstrip(".,!?")
    name = re.sub(r"\s+", " ", name)
    # Drop if LLM returned something that looks like the full question
    if len(name.split()) > 6:
        words = name.split()[:4]
        name = " ".join(words)
    return name[:200]


def _fallback_name(first_message: str) -> str:
    """Extract meaningful words from the message, skipping filler words."""
    cleaned = re.sub(r"\s+", " ", first_message).strip()
    if not cleaned:
        return "New Session"
    words = [
        w.strip(".,!?\"'")
        for w in re.split(r"\s+", cleaned)
        if w.strip(".,!?\"'").lower() not in _FILLER_WORDS and len(w) > 2
    ]
    short = " ".join(words[:4])
    return short[:200] or "New Session"


async def session_naming(
    ctx: dict[str, Any],
    session_id: str,
    first_message: str,
) -> dict[str, Any]:
    _LOGGER.info(
        "session_naming:start session_id=%s message_preview=%r",
        session_id,
        first_message[:120],
    )

    try:
        # Safely substitute user content to prevent prompt injection.
        # Escape braces first, then use .format() which is now safe.
        safe_message = first_message[:1000].replace("{", "{{").replace("}", "}}")
        raw = await ainvoke_text(
            alias="llama",
            prompt=_NAME_PROMPT.format(message=safe_message),
        )
        name = _clean_name(raw)
        if not name:
            raise ValueError("Empty name returned by LLM")
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("session_naming LLM call failed for %s: %s", session_id, exc)
        name = _fallback_name(first_message)
        _LOGGER.info("session_naming:fallback session_id=%s name=%r", session_id, name)

    try:
        session_factory = get_session_factory()
        async with session_factory() as db:
            result = await db.execute(select(Session).where(Session.id == session_id))
            session = result.scalar_one_or_none()
            if session is None:
                _LOGGER.warning("session_naming: session %s not found", session_id)
                return {"status": "not_found", "session_id": session_id}

            # Only set if not already manually named
            if session.name is None:
                session.name = name
                await db.commit()
                _LOGGER.info("session_naming:set session_id=%s name=%r", session_id, name)
            else:
                _LOGGER.info(
                    "session_naming:skip session_id=%s existing_name=%r",
                    session_id,
                    session.name,
                )
    except RuntimeError as exc:
        if "Event loop is closed" in str(exc):
            _LOGGER.warning("session_naming: skipped due to closed event loop for %s", session_id)
            return {"status": "event_loop_closed", "session_id": session_id}
        raise
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("session_naming: db update failed for %s: %s", session_id, exc)
        return {"status": "db_error", "session_id": session_id}

    return {"status": "ok", "session_id": session_id, "name": name}

