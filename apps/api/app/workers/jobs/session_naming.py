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
You are a concise session title generator. Given the user's first message, \
produce a short, descriptive title of 3–6 words that captures the topic. \
Output ONLY the title — no punctuation at the end, no quotes, no extra text.

User message:
{message}

Title:"""


def _clean_name(raw: str) -> str:
    """Strip quotes, trailing punctuation, and excessive whitespace."""
    name = raw.strip().strip('"\'').rstrip(".")
    # Collapse multiple spaces / newlines
    name = re.sub(r"\s+", " ", name)
    return name[:200]


def _fallback_name(first_message: str) -> str:
    cleaned = re.sub(r"\s+", " ", first_message).strip()
    if not cleaned:
        return "New Session"
    words = [word for word in re.split(r"\s+", cleaned) if word]
    short = " ".join(words[:6]).strip().strip('"\'').rstrip(".")
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
        raw = await ainvoke_text(
            alias="mistral-small",
            prompt=_NAME_PROMPT.format(message=first_message[:1000]),
        )
        name = _clean_name(raw)
        if not name:
            raise ValueError("Empty name returned by LLM")
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("session_naming LLM call failed for %s: %s", session_id, exc)
        name = _fallback_name(first_message)
        _LOGGER.info("session_naming:fallback session_id=%s name=%r", session_id, name)

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

    return {"status": "ok", "session_id": session_id, "name": name}

