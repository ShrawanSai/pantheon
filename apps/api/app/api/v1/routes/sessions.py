from __future__ import annotations

import json
from decimal import Decimal
import re
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.core.config import get_settings
from apps.api.app.db.models import (
    ToolCallEvent,
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
from apps.api.app.dependencies.rooms import get_owned_active_room_or_404
from apps.api.app.schemas.chat import SessionRead, TurnCreateRequest, TurnRead
from apps.api.app.services.llm.gateway import GatewayMessage, LlmGateway, get_llm_gateway
from apps.api.app.services.orchestration.context_manager import (
    ContextBudgetExceeded,
    ContextManager,
    ContextMessage,
    HistoryMessage,
)
from apps.api.app.services.orchestration.mode_executor import (
    LangGraphModeExecutor,
    ToolCallRecord,
    TurnExecutionInput,
    get_mode_executor,
)
from apps.api.app.services.orchestration.orchestrator_manager import route_turn
from apps.api.app.services.orchestration.summary_extractor import extract_summary_structure
from apps.api.app.services.orchestration.summary_generator import generate_summary_text
from apps.api.app.services.billing.wallet import WalletService, get_wallet_service
from apps.api.app.services.tools.permissions import get_permitted_tool_names
from apps.api.app.services.usage.meter import (
    compute_credits_burned,
    compute_oe_tokens,
    get_model_multiplier,
)
from apps.api.app.services.usage.recorder import UsageRecord, UsageRecorder, get_usage_recorder

router = APIRouter(tags=["sessions"])
_TAG_PATTERN = re.compile(r"@([a-zA-Z0-9_]+)")


def _session_to_read(session: Session) -> SessionRead:
    return SessionRead(
        id=session.id,
        room_id=session.room_id,
        started_by_user_id=session.started_by_user_id,
        created_at=session.created_at,
        deleted_at=session.deleted_at,
    )


def _extract_tagged_agent_keys(message: str) -> list[str]:
    tags = _TAG_PATTERN.findall(message)
    seen: set[str] = set()
    ordered: list[str] = []
    for tag in tags:
        normalized = tag.strip().lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            ordered.append(normalized)
    return ordered


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
    await get_owned_active_room_or_404(db, room_id=room_id, user_id=user_id)

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
    await get_owned_active_room_or_404(db, room_id=room_id, user_id=user_id)

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
    await get_owned_active_room_or_404(db, room_id=room_id, user_id=user_id)

    session = await db.scalar(
        select(Session).where(
            Session.id == session_id,
            Session.room_id == room_id,
            Session.deleted_at.is_(None),
        )
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    session.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/sessions/{session_id}/turns", response_model=TurnRead, status_code=status.HTTP_201_CREATED)
async def create_turn(
    session_id: str,
    payload: TurnCreateRequest,
    current_user: dict[str, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    mode_executor: LangGraphModeExecutor = Depends(get_mode_executor),
    llm_gateway: LlmGateway = Depends(get_llm_gateway),
    usage_recorder: UsageRecorder = Depends(get_usage_recorder),
    wallet_service: WalletService = Depends(get_wallet_service),
) -> TurnRead:
    user_id = current_user["user_id"]
    session, room = await _get_owned_active_session_or_404(db, session_id=session_id, user_id=user_id)

    agents = (
        await db.scalars(
            select(RoomAgent)
            .where(RoomAgent.room_id == room.id)
            .order_by(RoomAgent.position.asc(), RoomAgent.created_at.asc())
        )
    ).all()
    active_agent = agents[0] if agents else None
    manual_tag_selected_agents: list[RoomAgent] = []
    orchestrator_selected_agents: list[RoomAgent] = []
    settings = get_settings()

    if room.current_mode in {"manual", "tag"}:
        tagged_keys = _extract_tagged_agent_keys(payload.message)
        if not tagged_keys:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "no_valid_tagged_agents",
                    "message": "Manual mode requires at least one tagged agent (e.g., @writer).",
                },
            )
        by_key = {agent.agent_key.lower(): agent for agent in agents}
        manual_tag_selected_agents = [by_key[key] for key in tagged_keys if key in by_key]
        if not manual_tag_selected_agents:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "no_valid_tagged_agents",
                    "message": "No tagged agents matched this room.",
                },
            )
        active_agent = manual_tag_selected_agents[0]
    elif room.current_mode == "orchestrator":
        if not agents:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "no_room_agents",
                    "message": "Orchestrator mode requires at least one agent.",
                },
            )
        decision = await route_turn(
            agents=agents,
            user_input=payload.message,
            gateway=llm_gateway,
            manager_model_alias=settings.orchestrator_manager_model_alias,
        )
        by_key = {agent.agent_key.lower(): agent for agent in agents}
        orchestrator_selected_agents = [
            by_key[key.lower()] for key in decision.selected_agent_keys if key.lower() in by_key
        ]
        if not orchestrator_selected_agents:
            orchestrator_selected_agents = [agents[0]]
        active_agent = orchestrator_selected_agents[0]
    if room.current_mode == "roundtable" and not agents:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "no_room_agents",
                "message": "Round table mode requires at least one agent in the room.",
            },
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

    context_manager = _build_context_manager()
    if room.current_mode == "roundtable":
        system_messages = [
            ContextMessage(role="system", content=f"Room mode: {room.current_mode}"),
            ContextMessage(role="system", content=f"Room goal: {room.goal or 'No goal specified.'}"),
        ]
    else:
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

    next_turn_index = int(await db.scalar(select(func.max(Turn.turn_index)).where(Turn.session_id == session.id)) or 0)

    if room.current_mode == "roundtable":
        selected_agents = agents
    elif room.current_mode == "orchestrator":
        selected_agents = orchestrator_selected_agents or ([active_agent] if active_agent else [])
    elif room.current_mode in {"manual", "tag"}:
        selected_agents = manual_tag_selected_agents or ([active_agent] if active_agent else [])
    else:
        selected_agents = [active_agent]
    share_same_turn_outputs = room.current_mode in {"roundtable", "orchestrator"}
    prior_roundtable_outputs: list[GatewayMessage] = []
    assistant_entries: list[tuple[str, str]] = []
    usage_entries: list[tuple[str, str, int, int, int, int]] = []
    tool_event_entries: list[tuple[str | None, tuple[ToolCallRecord, ...]]] = []
    turn_status = "completed"

    for selected_agent in selected_agents:
        if selected_agent is None:
            selected_agent_name = "Assistant"
            selected_agent_alias = model_alias
            selected_agent_role = "Provide helpful responses."
        else:
            selected_agent_name = selected_agent.name
            selected_agent_alias = payload.model_alias_override or selected_agent.model_alias
            selected_agent_role = selected_agent.role_prompt

        request_messages: list[GatewayMessage] = [
            GatewayMessage(role="system", content=f"Agent role: {selected_agent_role}"),
            *[GatewayMessage(role=item.role, content=item.content) for item in context.messages],
            *prior_roundtable_outputs,
        ]
        allowed_tools = tuple(get_permitted_tool_names(selected_agent)) if selected_agent is not None else ()

        try:
            gateway_response = await mode_executor.run_turn(
                db,
                TurnExecutionInput(
                    model_alias=selected_agent_alias,
                    messages=request_messages,
                    max_output_tokens=settings.context_max_output_tokens,
                    thread_id=f"{session.id}:{next_turn_index + 1}:{selected_agent_name}",
                    allowed_tool_names=allowed_tools,
                    room_id=session.room_id,
                ),
            )
            assistant_entries.append((selected_agent_name, gateway_response.text))
            usage_entries.append(
                (
                    selected_agent_alias,
                    gateway_response.provider_model,
                    gateway_response.usage.input_tokens_fresh,
                    gateway_response.usage.input_tokens_cached,
                    gateway_response.usage.output_tokens,
                    gateway_response.usage.total_tokens,
                )
            )
            tool_event_entries.append(
                (
                    selected_agent.agent_key if selected_agent is not None else None,
                    gateway_response.tool_calls,
                )
            )
            if share_same_turn_outputs:
                prior_roundtable_outputs.append(
                    GatewayMessage(
                        role="assistant",
                        content=f"{selected_agent_name}: {gateway_response.text}",
                    )
                )
        except Exception as exc:
            turn_status = "partial"
            error_content = (
                f"[[agent_error]] agent={selected_agent_name} "
                f"type={exc.__class__.__name__} message={str(exc) or 'execution_failed'}"
            )
            assistant_entries.append((selected_agent_name, error_content))
            if share_same_turn_outputs:
                prior_roundtable_outputs.append(
                    GatewayMessage(role="assistant", content=f"{selected_agent_name}: {error_content}")
                )

    multi_agent_mode = len(selected_agents) > 1
    model_alias_marker = (
        "roundtable"
        if room.current_mode == "roundtable"
        else ("multi-agent" if room.current_mode == "orchestrator" and multi_agent_mode else model_alias)
    )
    assistant_output_text = (
        "\n\n".join([f"{name}: {content}" for name, content in assistant_entries])
        if multi_agent_mode
        else (assistant_entries[0][1] if assistant_entries else "")
    )

    turn = Turn(
        id=str(uuid4()),
        session_id=session.id,
        turn_index=next_turn_index + 1,
        mode=room.current_mode,
        user_input=payload.message,
        assistant_output=assistant_output_text,
        status=turn_status,
    )
    db.add(turn)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Turn creation conflicted with concurrent writes. Please retry.",
        ) from exc

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
        content=assistant_output_text,
    )
    db.add(user_message)
    if multi_agent_mode:
        for entry_agent_name, entry_content in assistant_entries:
            db.add(
                Message(
                    id=str(uuid4()),
                    turn_id=turn.id,
                    session_id=session.id,
                    role="assistant",
                    agent_name=entry_agent_name,
                    mode=room.current_mode,
                    content=entry_content,
                )
            )
    else:
        db.add(assistant_message)

    if context.generated_summary_text:
        generated = await generate_summary_text(
            raw_summary_text=context.generated_summary_text,
            gateway=llm_gateway,
            model_alias=settings.summarizer_model_alias,
        )
        structure = await extract_summary_structure(
            summary_text=generated.summary_text,
            gateway=llm_gateway,
            model_alias=settings.summarizer_model_alias,
        )
        summary = SessionSummary(
            id=str(uuid4()),
            session_id=session.id,
            from_message_id=context.summary_from_message_id,
            to_message_id=context.summary_to_message_id,
            summary_text=generated.summary_text,
            key_facts_json=json.dumps(structure.key_facts),
            open_questions_json=json.dumps(structure.open_questions),
            decisions_json=json.dumps(structure.decisions),
            action_items_json=json.dumps(structure.action_items),
        )
        db.add(summary)

    audit = TurnContextAudit(
        id=str(uuid4()),
        turn_id=turn.id,
        session_id=session.id,
        model_alias=model_alias_marker,
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

    for (
        usage_model_alias,
        usage_provider_model,
        usage_input_fresh,
        usage_input_cached,
        usage_output,
        usage_total,
    ) in usage_entries:
        oe_tokens = compute_oe_tokens(
            input_tokens_fresh=usage_input_fresh,
            input_tokens_cached=usage_input_cached,
            output_tokens=usage_output,
        )
        credits_burned = compute_credits_burned(
            oe_tokens,
            model_multiplier=get_model_multiplier(usage_model_alias),
        )
        await usage_recorder.stage_llm_usage(
            db,
            UsageRecord(
                user_id=user_id,
                room_id=session.room_id,
                session_id=session.id,
                turn_id=turn.id,
                model_alias=usage_model_alias,
                provider_model=usage_provider_model,
                input_tokens_fresh=usage_input_fresh,
                input_tokens_cached=usage_input_cached,
                output_tokens=usage_output,
                total_tokens=usage_total,
                oe_tokens_computed=oe_tokens,
                credits_burned=credits_burned,
                recorded_at=datetime.now(timezone.utc),
            ),
        )
        await wallet_service.stage_debit(
            db,
            user_id=user_id,
            credits_burned=credits_burned,
            reference_id=turn.id,
            note=f"turn:{turn.id}",
        )

    for agent_key, tool_calls in tool_event_entries:
        for tool_call in tool_calls:
            db.add(
                ToolCallEvent(
                    id=str(uuid4()),
                    user_id=user_id,
                    room_id=session.room_id,
                    session_id=session.id,
                    turn_id=turn.id,
                    agent_key=agent_key,
                    tool_name=tool_call.tool_name,
                    tool_input_json=tool_call.input_json,
                    tool_output_json=tool_call.output_json,
                    status=tool_call.status,
                    latency_ms=tool_call.latency_ms,
                    credits_charged=Decimal("0"),
                    created_at=datetime.now(timezone.utc),
                )
            )

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Turn creation conflicted with concurrent writes. Please retry.",
        ) from exc
    await db.refresh(turn)

    return TurnRead(
        id=turn.id,
        session_id=turn.session_id,
        turn_index=turn.turn_index,
        mode=turn.mode,
        user_input=turn.user_input,
        assistant_output=turn.assistant_output or "",
        status=turn.status,
        model_alias_used=model_alias_marker,
        summary_triggered=context.summary_triggered,
        prune_triggered=context.prune_triggered,
        overflow_rejected=False,
        created_at=turn.created_at,
    )
