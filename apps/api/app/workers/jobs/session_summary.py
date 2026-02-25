from __future__ import annotations

import json
import logging
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from apps.api.app.core.config import get_settings
from apps.api.app.db.session import get_session_factory
from apps.api.app.db.models import Message, SessionSummary
from apps.api.app.services.llm.gateway import OpenAICompatibleGateway
from apps.api.app.services.orchestration.summary_extractor import extract_summary_structure
from apps.api.app.services.orchestration.summary_generator import generate_summary_text

_LOGGER = logging.getLogger(__name__)


async def session_summary(
    ctx: dict[str, Any],
    session_id: str,
    from_message_id: str,
    to_message_id: str,
) -> dict[str, Any]:
    _LOGGER.info(
        "Starting background summarization for session %s (messages %s to %s)",
        session_id,
        from_message_id,
        to_message_id,
    )

    session_factory = get_session_factory()
    async with session_factory() as db:
        result = await db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .where(Message.visibility == "shared")
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
        messages = list(result.scalars().all())

    start_idx = -1
    end_idx = -1
    for i, msg in enumerate(messages):
        if msg.id == from_message_id:
            start_idx = i
        if msg.id == to_message_id:
            end_idx = i

    if start_idx == -1 or end_idx == -1 or start_idx > end_idx:
        _LOGGER.warning(
            "Could not find strict range of messages for summarization %s. Reverting to best effort bounds.",
            session_id,
        )
        if start_idx == -1:
            start_idx = 0
        if end_idx == -1:
            end_idx = len(messages) - 1

    truncated = messages[start_idx : end_idx + 1]
    raw_summary_text = "\n".join(f"{m.role}: {m.content}" for m in truncated)

    if not raw_summary_text.strip():
        _LOGGER.warning("No valid text to summarize for session %s, aborting job.", session_id)
        return {"status": "aborted", "reason": "no_text"}

    settings = get_settings()
    gateway = OpenAICompatibleGateway()

    try:
        generated = await generate_summary_text(
            raw_summary_text=raw_summary_text,
            gateway=gateway,
            model_alias=settings.summarizer_model_alias,
        )

        structure = await extract_summary_structure(
            summary_text=generated.summary_text,
            gateway=gateway,
            model_alias=settings.summarizer_model_alias,
        )

        session_factory = get_session_factory()
        async with session_factory() as db:
            db.add(
                SessionSummary(
                    id=str(uuid4()),
                    session_id=session_id,
                    from_message_id=from_message_id,
                    to_message_id=to_message_id,
                    summary_text=generated.summary_text,
                    key_facts_json=json.dumps(structure.key_facts),
                    open_questions_json=json.dumps(structure.open_questions),
                    decisions_json=json.dumps(structure.decisions),
                    action_items_json=json.dumps(structure.action_items),
                )
            )
            await db.commit()
            
        _LOGGER.info("Completed background summarization for session %s", session_id)
        return {"status": "success", "session_id": session_id}
    except Exception as exc:
        _LOGGER.error("Background summarization failed for session %s: %s", session_id, exc)
        raise
