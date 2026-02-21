from __future__ import annotations

import json
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.core.config import get_settings
from apps.api.app.db.models import (
    Message,
    Room,
    RoomAgent,
    Session,
    SessionSummary,
    Turn,
    TurnContextAudit,
)
from apps.api.app.db.session import get_db
from apps.api.app.dependencies.auth import get_current_user
from apps.api.app.schemas.chat import SessionRead, TurnCreateRequest, TurnRead
from apps.api.app.services.llm.gateway import GatewayMessage, GatewayRequest, LlmGateway, get_llm_gateway
from apps.api.app.services.orchestration.context_manager import (
    ContextBudgetExceeded,
    ContextManager,
    ContextMessage,
    HistoryMessage,
)
from apps.api.app.services.usage.meter import compute_credits_burned, compute_oe_tokens
from apps.api.app.services.usage.recorder import UsageRecord, UsageRecorder, get_usage_recorder

router = APIRouter(tags=["sessions"])


def _session_to_read(session: Session) -> SessionRead:
    return SessionRead(
        id=session.id,
        room_id=session.room_id,
        started_by_user_id=session.started_by_user_id,
        created_at=session.created_at,
        deleted_at=session.deleted_at,
    )


async def _get_owned_active_room_or_404(db: AsyncSession, *, room_id: str, user_id: str) -> Room:
    room = await db.scalar(
        select(Room).where(
            Room.id == room_id,
            Room.owner_user_id == user_id,
            Room.deleted_at.is_(None),
        )
    )
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found.")
    return room


async def _get_owned_active_session_or_404(
    db: AsyncSession, *, session_id: str, user_id: str
) -> tuple[Session, Room]:
    session = await db.scalar(
        select(Session)
        .join(Room, Room.id == Session.room_id)
        .where(
            Session.id == session_id,
            Session.deleted_at.is_(None),
            Room.owner_user_id == user_id,
            Room.deleted_at.is_(None),
        )
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    room = await db.get(Room, session.room_id)
    if room is None or room.deleted_at is not None or room.owner_user_id != user_id:
        raise HTTPException(status_code=404, detail="Session not found.")
    return session, room


def _build_context_manager() -> ContextManager:
    settings = get_settings()
    return ContextManager(
        max_output_tokens=settings.context_max_output_tokens,
        summary_trigger_ratio=settings.context_summary_trigger_ratio,
        prune_trigger_ratio=settings.context_prune_trigger_ratio,
        mandatory_summary_turn=settings.context_mandatory_summary_turn,
        recent_turns_to_keep=settings.context_recent_turns_to_keep,
    )


@router.post("/rooms/{room_id}/sessions", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
async def create_session(
    room_id: str,
    current_user: dict[str, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionRead:
    user_id = current_user["user_id"]
    await _get_owned_active_room_or_404(db, room_id=room_id, user_id=user_id)

    session = Session(
        id=str(uuid4()),
        room_id=room_id,
        started_by_user_id=user_id,
        deleted_at=None,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return _session_to_read(session)


@router.get("/rooms/{room_id}/sessions", response_model=list[SessionRead])
async def list_sessions(
    room_id: str,
    current_user: dict[str, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SessionRead]:
    user_id = current_user["user_id"]
    await _get_owned_active_room_or_404(db, room_id=room_id, user_id=user_id)

    result = await db.scalars(
        select(Session)
        .where(
            Session.room_id == room_id,
            Session.deleted_at.is_(None),
        )
        .order_by(Session.created_at.desc())
    )
    return [_session_to_read(item) for item in result.all()]


@router.delete("/rooms/{room_id}/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    room_id: str,
    session_id: str,
    current_user: dict[str, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    user_id = current_user["user_id"]
    await _get_owned_active_room_or_404(db, room_id=room_id, user_id=user_id)

    session = await db.scalar(
        select(Session).where(
            Session.id == session_id,
            Session.room_id == room_id,
            Session.deleted_at.is_(None),
        )
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    session.deleted_at = datetime.now()
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/sessions/{session_id}/turns", response_model=TurnRead, status_code=status.HTTP_201_CREATED)
async def create_turn(
    session_id: str,
    payload: TurnCreateRequest,
    current_user: dict[str, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    llm_gateway: LlmGateway = Depends(get_llm_gateway),
    usage_recorder: UsageRecorder = Depends(get_usage_recorder),
) -> TurnRead:
    user_id = current_user["user_id"]
    session, room = await _get_owned_active_session_or_404(db, session_id=session_id, user_id=user_id)

    active_agent = await db.scalar(
        select(RoomAgent)
        .where(RoomAgent.room_id == room.id)
        .order_by(RoomAgent.position.asc(), RoomAgent.created_at.asc())
    )
    model_alias = payload.model_alias_override or (active_agent.model_alias if active_agent else "deepseek")
    agent_name = active_agent.name if active_agent else "Assistant"
    agent_role_prompt = active_agent.role_prompt if active_agent else "Provide helpful responses."

    history = (
        await db.scalars(
            select(Message)
            .where(Message.session_id == session.id)
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
    ).all()
    latest_summary = await db.scalar(
        select(SessionSummary)
        .where(SessionSummary.session_id == session.id)
        .order_by(SessionSummary.created_at.desc())
    )

    if latest_summary is None:
        turn_count_since_summary = int(
            await db.scalar(select(func.count(Turn.id)).where(Turn.session_id == session.id)) or 0
        )
    else:
        turn_count_since_summary = int(
            await db.scalar(
                select(func.count(Turn.id)).where(
                    Turn.session_id == session.id,
                    Turn.created_at > latest_summary.created_at,
                )
            )
            or 0
        )

    settings = get_settings()
    context_manager = _build_context_manager()
    system_messages = [
        ContextMessage(role="system", content=f"Room mode: {room.current_mode}"),
        ContextMessage(role="system", content=f"Room goal: {room.goal or 'No goal specified.'}"),
        ContextMessage(role="system", content=f"Agent role: {agent_role_prompt}"),
    ]
    history_messages = [
        HistoryMessage(
            id=message.id,
            role="assistant" if message.role == "assistant" else "user",
            content=message.content,
            turn_id=message.turn_id,
        )
        for message in history
        if message.role in {"user", "assistant"}
    ]

    try:
        context = context_manager.prepare(
            model_context_limit=settings.context_default_model_limit,
            system_messages=system_messages,
            history_messages=history_messages,
            latest_summary_text=latest_summary.summary_text if latest_summary else None,
            turn_count_since_last_summary=turn_count_since_summary,
            user_input=payload.message,
        )
    except ContextBudgetExceeded as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "context_budget_exceeded",
                "message": "Input exceeds session context budget. Shorten input or start a new session.",
                "input_budget": exc.input_budget,
                "estimated_tokens": exc.estimated_tokens,
                "model_context_limit": exc.model_context_limit,
            },
        ) from exc

    gateway_request = GatewayRequest(
        model_alias=model_alias,
        messages=[GatewayMessage(role=item.role, content=item.content) for item in context.messages],
        max_output_tokens=settings.context_max_output_tokens,
    )
    gateway_response = await llm_gateway.generate(gateway_request)

    next_turn_index = int(await db.scalar(select(func.max(Turn.turn_index)).where(Turn.session_id == session.id)) or 0)
    turn = Turn(
        id=str(uuid4()),
        session_id=session.id,
        turn_index=next_turn_index + 1,
        mode=room.current_mode,
        user_input=payload.message,
        assistant_output=gateway_response.text,
        status="completed",
    )
    db.add(turn)
    await db.flush()

    user_message = Message(
        id=str(uuid4()),
        turn_id=turn.id,
        session_id=session.id,
        role="user",
        agent_name=None,
        mode=room.current_mode,
        content=payload.message,
    )
    assistant_message = Message(
        id=str(uuid4()),
        turn_id=turn.id,
        session_id=session.id,
        role="assistant",
        agent_name=agent_name,
        mode=room.current_mode,
        content=gateway_response.text,
    )
    db.add(user_message)
    db.add(assistant_message)

    if context.generated_summary_text:
        summary = SessionSummary(
            id=str(uuid4()),
            session_id=session.id,
            from_message_id=context.summary_from_message_id,
            to_message_id=context.summary_to_message_id,
            summary_text=context.generated_summary_text,
            key_facts_json=json.dumps([]),
            open_questions_json=json.dumps([]),
            decisions_json=json.dumps([]),
            action_items_json=json.dumps([]),
        )
        db.add(summary)

    audit = TurnContextAudit(
        id=str(uuid4()),
        turn_id=turn.id,
        session_id=session.id,
        model_alias=model_alias,
        model_context_limit=context.model_context_limit,
        input_budget=context.input_budget,
        estimated_input_tokens_before=context.estimated_input_tokens_before,
        estimated_input_tokens_after_summary=context.estimated_input_tokens_after_summary,
        estimated_input_tokens_after_prune=context.estimated_input_tokens_after_prune,
        summary_triggered=context.summary_triggered,
        prune_triggered=context.prune_triggered,
        overflow_rejected=context.overflow_rejected,
        output_reserve=context.output_reserve,
        overhead_reserve=context.overhead_reserve,
    )
    db.add(audit)
    await db.commit()
    await db.refresh(turn)

    oe_tokens = compute_oe_tokens(
        input_tokens_fresh=gateway_response.usage.input_tokens_fresh,
        input_tokens_cached=gateway_response.usage.input_tokens_cached,
        output_tokens=gateway_response.usage.output_tokens,
    )
    credits_burned = compute_credits_burned(oe_tokens)
    await usage_recorder.record_llm_usage(
        UsageRecord(
            user_id=user_id,
            session_id=session.id,
            turn_id=turn.id,
            model_alias=model_alias,
            provider_model=gateway_response.provider_model,
            input_tokens_fresh=gateway_response.usage.input_tokens_fresh,
            input_tokens_cached=gateway_response.usage.input_tokens_cached,
            output_tokens=gateway_response.usage.output_tokens,
            total_tokens=gateway_response.usage.total_tokens,
            oe_tokens_computed=oe_tokens,
            credits_burned=credits_burned,
            recorded_at=datetime.now(),
        )
    )

    return TurnRead(
        id=turn.id,
        session_id=turn.session_id,
        turn_index=turn.turn_index,
        mode=turn.mode,
        user_input=turn.user_input,
        assistant_output=turn.assistant_output or "",
        status=turn.status,
        model_alias_used=model_alias,
        summary_triggered=context.summary_triggered,
        prune_triggered=context.prune_triggered,
        overflow_rejected=False,
        created_at=turn.created_at,
    )

