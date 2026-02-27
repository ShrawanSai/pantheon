from __future__ import annotations

from dataclasses import dataclass
import json
from collections.abc import AsyncIterator
from decimal import Decimal
import logging
import typing
import re
import time
from datetime import datetime, timezone, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.core.config import get_settings
from apps.api.app.db.models import (
    Agent,
    ToolCallEvent,
    Message,
    Room,
    RoomAgent,
    Session,
    SessionSummary,
    Turn,
    TurnContextAudit,
    UploadedFile,
)
from apps.api.app.db.session import get_db
from apps.api.app.dependencies.auth import get_current_user
from apps.api.app.dependencies.rooms import get_owned_active_room_or_404
from apps.api.app.schemas.chat import SessionRead, TurnCreateRequest, TurnRead
from apps.api.app.schemas.chat import (
    SessionMessageListRead,
    SessionMessageRead,
    SessionTurnHistoryRead,
    SessionTurnListRead,
)
from apps.api.app.services.llm.gateway import (
    GatewayMessage,
    GatewayRequest,
    LlmGateway,
    StreamingContext,
    get_llm_gateway,
)
from apps.api.app.services.orchestration.context_manager import (
    ContextBudgetExceeded,
    ContextManager,
    ContextMessage,
    HistoryMessage,
)
from apps.api.app.services.orchestration.mode_executor import (
    ActiveAgent,
    ToolCallRecord,
    TurnExecutor,
    TurnExecutionState,
    get_mode_executor,
)
from apps.api.app.services.orchestration.summary_extractor import extract_summary_structure
from apps.api.app.services.orchestration.summary_generator import generate_summary_text
from apps.api.app.services.billing.enforcement import get_enforcement_enabled
from apps.api.app.services.billing.wallet import WalletService, get_wallet_service
from apps.api.app.services.tools.permissions import get_permitted_tool_names
from apps.api.app.utils.decimal_format import format_decimal
from apps.api.app.services.usage.meter import (
    compute_credits_burned,
    compute_oe_tokens,
    get_model_multiplier,
)
from apps.api.app.services.usage.recorder import UsageRecord, UsageRecorder, get_usage_recorder

router = APIRouter(tags=["sessions"])
_TAG_PATTERN = re.compile(r"@([a-zA-Z0-9_]+)")
_LOGGER = logging.getLogger(__name__)


# Removed _SelectedAgent, using ActiveAgent


def _session_to_read(session: Session) -> SessionRead:
    return SessionRead(
        id=session.id,
        room_id=session.room_id,
        agent_id=session.agent_id,
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
) -> tuple[Session, Room | None, Agent | None]:
    session = await db.get(Session, session_id)
    if session is None or session.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Session not found.")

    if session.room_id is not None:
        room = await db.get(Room, session.room_id)
        if room is None or room.deleted_at is not None or room.owner_user_id != user_id:
            raise HTTPException(status_code=404, detail="Session not found.")
        return session, room, None

    if session.agent_id is not None:
        agent = await db.get(Agent, session.agent_id)
        if agent is None or agent.deleted_at is not None or agent.owner_user_id != user_id:
            raise HTTPException(status_code=404, detail="Session not found.")
        return session, None, agent

    raise HTTPException(status_code=404, detail="Session not found.")


async def _get_owned_active_agent_or_404(db: AsyncSession, *, agent_id: str, user_id: str) -> Agent:
    agent = await db.scalar(
        select(Agent).where(
            Agent.id == agent_id,
            Agent.owner_user_id == user_id,
            Agent.deleted_at.is_(None),
        )
    )
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found.")
    return agent


def _room_agent_to_selected_agent(room_agent: RoomAgent) -> ActiveAgent:
    if room_agent.agent is None:
        raise HTTPException(status_code=500, detail="Room agent assignment missing linked agent.")
    linked = room_agent.agent
    return ActiveAgent(
        agent_id=linked.id,
        agent_key=linked.agent_key,
        name=linked.name,
        model_alias=linked.model_alias,
        role_prompt=linked.role_prompt,
        tool_permissions=tuple(get_permitted_tool_names(linked)),
    )


def _standalone_agent_to_selected_agent(agent: Agent) -> ActiveAgent:
    return ActiveAgent(
        agent_id=agent.id,
        agent_key=agent.agent_key,
        name=agent.name,
        model_alias=agent.model_alias,
        role_prompt=agent.role_prompt,
        tool_permissions=tuple(get_permitted_tool_names(agent)),
    )


def _build_context_manager() -> ContextManager:
    settings = get_settings()
    return ContextManager(
        max_output_tokens=settings.context_max_output_tokens,
        summary_trigger_ratio=settings.context_summary_trigger_ratio,
        prune_trigger_ratio=settings.context_prune_trigger_ratio,
        mandatory_summary_turn=settings.context_mandatory_summary_turn,
        recent_turns_to_keep=settings.context_recent_turns_to_keep,
    )


def _sse_event(payload: dict[str, object]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _redis_incr_with_ttl(redis_pool: object, key: str, ttl_seconds: int) -> int:
    incr = getattr(redis_pool, "incr", None)
    if callable(incr):
        value = await incr(key)
    else:
        value = await redis_pool.execute_command("INCR", key)  # pragma: no cover
    value_int = int(value)

    expire = getattr(redis_pool, "expire", None)
    if value_int == 1 and callable(expire):
        await expire(key, ttl_seconds)
    elif value_int == 1:
        await redis_pool.execute_command("EXPIRE", key, ttl_seconds)  # pragma: no cover
    return value_int


async def check_turn_rate_limit(user_id: str, redis_pool: object | None, settings) -> None:
    if redis_pool is None:
        _LOGGER.warning("Rate limiting skipped: Redis pool unavailable.")
        return

    now = int(time.time())
    minute_bucket = now // 60
    hour_bucket = now // 3600
    minute_key = f"ratelimit:{user_id}:turns:{minute_bucket}"
    hour_key = f"ratelimit:{user_id}:turns:{hour_bucket}"

    try:
        minute_count = await _redis_incr_with_ttl(redis_pool, minute_key, ttl_seconds=60)
        hour_count = await _redis_incr_with_ttl(redis_pool, hour_key, ttl_seconds=3600)
    except Exception as exc:
        _LOGGER.warning("Rate limiting skipped: Redis error: %s", exc)
        return

    if minute_count > settings.rate_limit_turns_per_minute:
        retry_after_seconds = max(1, 60 - (now % 60))
        raise HTTPException(
            status_code=429,
            detail={"detail": "rate limit exceeded", "retry_after_seconds": retry_after_seconds},
            headers={"Retry-After": str(retry_after_seconds)},
        )
    if hour_count > settings.rate_limit_turns_per_hour:
        retry_after_seconds = max(1, 3600 - (now % 3600))
        raise HTTPException(
            status_code=429,
            detail={"detail": "rate limit exceeded", "retry_after_seconds": retry_after_seconds},
            headers={"Retry-After": str(retry_after_seconds)},
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
        agent_id=None,
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


@router.post("/agents/{agent_id}/sessions", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
async def create_agent_session(
    agent_id: str,
    current_user: dict[str, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionRead:
    user_id = current_user["user_id"]
    await _get_owned_active_agent_or_404(db, agent_id=agent_id, user_id=user_id)

    session = Session(
        id=str(uuid4()),
        room_id=None,
        agent_id=agent_id,
        started_by_user_id=user_id,
        deleted_at=None,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return _session_to_read(session)


@router.get("/agents/{agent_id}/sessions", response_model=list[SessionRead])
async def list_agent_sessions(
    agent_id: str,
    current_user: dict[str, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SessionRead]:
    user_id = current_user["user_id"]
    await _get_owned_active_agent_or_404(db, agent_id=agent_id, user_id=user_id)

    result = await db.scalars(
        select(Session)
        .where(
            Session.agent_id == agent_id,
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


@router.get("/sessions/{session_id}/messages", response_model=SessionMessageListRead)
async def get_session_messages(
    session_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: dict[str, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionMessageListRead:
    user_id = current_user["user_id"]
    session, _, _ = await _get_owned_active_session_or_404(db, session_id=session_id, user_id=user_id)
    conditions = (Message.session_id == session.id,)
    total = int(await db.scalar(select(func.count(Message.id)).where(*conditions)) or 0)
    rows_list = (await db.scalars(
        select(Message)
        .where(*conditions)
        .order_by(
            Message.created_at.desc(),
            case((Message.role == "user", 1), else_=0).desc(),
            Message.id.desc(),
        )
        .limit(limit)
        .offset(offset)
    )).all()
    rows_list.reverse()
    return SessionMessageListRead(
        messages=[
            SessionMessageRead(
                id=row.id,
                role=row.role,
                agent_name=row.agent_name,
                content=row.content,
                turn_id=row.turn_id,
                created_at=row.created_at,
            )
            for row in rows_list
        ],
        total=total,
    )


@router.get("/sessions/{session_id}/turns", response_model=SessionTurnListRead)
async def get_session_turns(
    session_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: dict[str, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionTurnListRead:
    user_id = current_user["user_id"]
    session, _, _ = await _get_owned_active_session_or_404(db, session_id=session_id, user_id=user_id)
    conditions = (Turn.session_id == session.id,)
    total = int(await db.scalar(select(func.count(Turn.id)).where(*conditions)) or 0)
    rows = await db.scalars(
        select(Turn)
        .where(*conditions)
        .order_by(Turn.turn_index.asc(), Turn.created_at.asc())
        .limit(limit)
        .offset(offset)
    )
    return SessionTurnListRead(
        turns=[
            SessionTurnHistoryRead(
                id=row.id,
                turn_index=row.turn_index,
                mode=row.mode,
                user_input=row.user_input,
                assistant_output=row.assistant_output or "",
                status=row.status,
                created_at=row.created_at,
            )
            for row in rows.all()
        ],
        total=total,
    )


@router.post("/sessions/{session_id}/turns", response_model=TurnRead, status_code=status.HTTP_201_CREATED)
async def create_turn(
    session_id: str,
    payload: TurnCreateRequest,
    request: Request,
    current_user: dict[str, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    mode_executor: TurnExecutor = Depends(get_mode_executor),
    llm_gateway: LlmGateway = Depends(get_llm_gateway),
    usage_recorder: UsageRecorder = Depends(get_usage_recorder),
    wallet_service: WalletService = Depends(get_wallet_service),
) -> TurnRead:
    user_id = current_user["user_id"]
    settings = get_settings()
    await check_turn_rate_limit(user_id, getattr(request.app.state, "arq_redis", None), settings)
    session, room, standalone_agent = await _get_owned_active_session_or_404(
        db, session_id=session_id, user_id=user_id
    )

    room_agents: list[RoomAgent] = []
    selected_agents: list[ActiveAgent] = []
    active_agent: ActiveAgent | None = None
    turn_mode: str

    if room is not None:
        room_agents = (
            await db.scalars(
                select(RoomAgent)
                .options(selectinload(RoomAgent.agent))
                .join(Agent, Agent.id == RoomAgent.agent_id)
                .where(
                    RoomAgent.room_id == room.id,
                    Agent.deleted_at.is_(None),
                )
                .order_by(RoomAgent.position.asc(), RoomAgent.created_at.asc())
            )
        ).all()
        manual_tag_selected_agents: list[RoomAgent] = []
        tagged_keys = _extract_tagged_agent_keys(payload.message)
        by_key = {assignment.agent.agent_key.lower(): assignment for assignment in room_agents}
        manual_tag_selected_agents = [by_key[key] for key in tagged_keys if key in by_key]

        turn_mode = room.current_mode

        if manual_tag_selected_agents:
            if len(manual_tag_selected_agents) > 1:
                turn_mode = "roundtable"
            else:
                turn_mode = "tag"
            active_room_agent = manual_tag_selected_agents[0]
            selected_assignments = manual_tag_selected_agents
        elif room.current_mode in {"manual", "tag"}:
            if not tagged_keys:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "no_valid_tagged_agents",
                        "message": "Manual mode requires at least one tagged agent (e.g., @writer).",
                    },
                )
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "no_valid_tagged_agents",
                    "message": "No tagged agents matched this room.",
                },
            )
        elif room.current_mode == "orchestrator":
            if not room_agents:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "no_room_agents",
                        "message": "Orchestrator mode requires at least one agent.",
                    },
                )
            active_room_agent = room_agents[0]
            selected_assignments = room_agents
        elif room.current_mode == "roundtable":
            if not room_agents:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "no_room_agents",
                        "message": "Round table mode requires at least one agent in the room.",
                    },
                )
            active_room_agent = room_agents[0]
            selected_assignments = room_agents
        else:
            selected_assignments = [active_room_agent] if active_room_agent is not None else []

        selected_agents = [_room_agent_to_selected_agent(assignment) for assignment in selected_assignments]
        active_agent = _room_agent_to_selected_agent(active_room_agent) if active_room_agent else None
    else:
        if standalone_agent is None:
            raise HTTPException(status_code=404, detail="Session not found.")
        active_agent = _standalone_agent_to_selected_agent(standalone_agent)
        selected_agents = [active_agent]
        turn_mode = "standalone"

    if get_enforcement_enabled(settings.credit_enforcement_enabled):
        wallet = await wallet_service.get_or_create_wallet(db, user_id=user_id)
        wallet_balance = wallet.balance if wallet.balance is not None else Decimal("0")
        if wallet_balance <= Decimal("0"):
            raise HTTPException(
                status_code=402,
                detail="Insufficient credits. Please top up your account.",
            )
    model_alias = payload.model_alias_override or (active_agent.model_alias if active_agent else "deepseek")

    history_rows = (
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
    next_turn_index = int(await db.scalar(select(func.max(Turn.turn_index)).where(Turn.session_id == session.id)) or 0)

    summary_used_fallback = False
    last_debit_balance: Decimal | None = None

    history_messages: list[HistoryMessage] = []
    if room is not None:
        combined = sorted(history_rows, key=lambda item: (item.created_at, item.id))
    else:
        combined = [item for item in history_rows if item.visibility == "shared"]

    for message in combined:
        if message.role not in {"user", "assistant", "tool"}:
            continue
        role = "user" if message.role == "user" else "assistant"
        content = message.content
        if message.role == "assistant":
            # Strip legacy hallucinated tags like [Sundar]: or Sundar: from the stored content
            content = re.sub(r'^\[.*?\]:\s*', '', content)
            # Only strip Name: if it looks like a prefix (not just the start of a sentence)
            # We use a non-greedy match and check for a following space
            content = re.sub(r'^[A-Za-z0-9_\s]{2,20}:\s*', '', content)

        if room is not None and message.role == "assistant" and message.visibility == "shared":
            content = f"{message.agent_name or message.source_agent_key}: {content}"
        history_messages.append(
            HistoryMessage(
                id=message.id,
                role=role,
                content=content,
                turn_id=message.turn_id,
            )
        )

    system_messages = []
    if room is not None:
        system_messages.append(ContextMessage(role="system", content=f"Room mode: {turn_mode}"))
        if room.goal:
            system_messages.append(ContextMessage(role="system", content=f"Room goal: {room.goal}"))
    else:
        system_messages.append(ContextMessage(role="system", content="Session mode: standalone"))

    try:
        primary_context = context_manager.prepare(
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

    import typing
    state = TurnExecutionState(
        session_id=session.id,
        turn_index=next_turn_index + 1,
        user_input=payload.message,
        room_mode=typing.cast(typing.Any, turn_mode),
        active_agents=selected_agents,
        primary_context_messages=[GatewayMessage(role=m.role, content=m.content) for m in primary_context.messages],
        max_output_tokens=settings.context_max_output_tokens,
        room_id=session.room_id,
    )

    state = await mode_executor.run_turn(db, state)

    if not state.assistant_entries and not state.final_synthesis and state.current_status != "failed":
        raise HTTPException(status_code=422, detail="No executable agent found for this turn.")

    model_alias_for_marker = model_alias
    if turn_mode == "orchestrator" and state.usage_entries:
        model_alias_for_marker = state.usage_entries[0][1]
    multi_agent_mode = state.total_invocations > 1 if turn_mode == "orchestrator" else len(selected_agents) > 1
    model_alias_marker = (
        "roundtable"
        if turn_mode == "roundtable"
        else ("multi-agent" if turn_mode == "orchestrator" and multi_agent_mode else model_alias_for_marker)
    )

    if turn_mode == "orchestrator" and state.per_round_entries:
        if len(state.per_round_entries) > 1:
            round_blocks: list[str] = []
            for round_idx, round_entries in enumerate(state.per_round_entries, start=1):
                lines = [f"[Round {round_idx}]"]
                lines.extend(f"{entry_agent.name}: {content}" for entry_agent, content in round_entries)
                round_blocks.append("\n".join(lines))
            assistant_output_text = "\n\n".join(round_blocks)
        else:
            single_round = state.per_round_entries[0]
            assistant_output_text = (
                "\n\n".join(f"{entry_agent.name}: {content}" for entry_agent, content in single_round)
                if len(single_round) > 1
                else (single_round[0][1] if single_round else "")
            )
    else:
        assistant_output_text = (
            "\n\n".join([f"{entry_agent.name}: {content}" for entry_agent, content in state.assistant_entries])
            if multi_agent_mode
            else (state.assistant_entries[0][1] if state.assistant_entries else "")
        )
    if state.final_synthesis:
        synthesis_block = f"Manager synthesis:\n{state.final_synthesis}"
        assistant_output_text = (
            f"{assistant_output_text}\n\n---\n\n{synthesis_block}" if assistant_output_text else synthesis_block
        )

    turn = Turn(
        id=str(uuid4()),
        session_id=session.id,
        turn_index=next_turn_index + 1,
        mode=turn_mode,
        user_input=payload.message,
        assistant_output=assistant_output_text,
        status=state.current_status,
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
        visibility="shared",
        agent_key=None,
        source_agent_key=None,
        agent_name=None,
        mode=turn_mode,
        content=payload.message,
    )
    db.add(user_message)
    for trace_agent, tool_calls in state.tool_trace_entries:
        for tool_call in tool_calls:
            db.add(
                Message(
                    id=str(uuid4()),
                    turn_id=turn.id,
                    session_id=session.id,
                    role="assistant",
                    visibility="private",
                    agent_key=trace_agent.agent_key,
                    source_agent_key=trace_agent.agent_key,
                    agent_name=trace_agent.name,
                    mode=turn_mode,
                    content=f"{tool_call.tool_name}({tool_call.input_json})",
                )
            )
            db.add(
                Message(
                    id=str(uuid4()),
                    turn_id=turn.id,
                    session_id=session.id,
                    role="tool",
                    visibility="private",
                    agent_key=trace_agent.agent_key,
                    source_agent_key=trace_agent.agent_key,
                    agent_name=trace_agent.name,
                    mode=turn_mode,
                    content=tool_call.output_json,
                )
            )

    for entry_agent, entry_content in state.assistant_entries:
        db.add(
            Message(
                id=str(uuid4()),
                turn_id=turn.id,
                session_id=session.id,
                role="assistant",
                visibility="shared",
                agent_key=entry_agent.agent_key,
                source_agent_key=entry_agent.agent_key,
                agent_name=entry_agent.name,
                mode=turn_mode,
                content=entry_content,
            )
        )
    if state.final_synthesis:
        db.add(
            Message(
                id=str(uuid4()),
                turn_id=turn.id,
                session_id=session.id,
                role="assistant",
                visibility="shared",
                agent_key="manager",
                source_agent_key="manager",
                agent_name="Manager",
                mode=turn_mode,
                content=state.final_synthesis,
            )
        )

    if primary_context.summary_triggered:
        from arq import ArqRedis
        redis_pool: ArqRedis | None = getattr(request.app.state, "arq_redis", None)
        if redis_pool:
            await redis_pool.enqueue_job(
                "session_summary",
                session.id,
                primary_context.summary_from_message_id,
                primary_context.summary_to_message_id,
            )
        else:
            _LOGGER.warning("arq_redis not found in app state; skipping async summarization for session %s", session.id)

    audit = TurnContextAudit(
        id=str(uuid4()),
        turn_id=turn.id,
        session_id=session.id,
        model_alias=model_alias_marker,
        model_context_limit=primary_context.model_context_limit,
        input_budget=primary_context.input_budget,
        estimated_input_tokens_before=primary_context.estimated_input_tokens_before,
        estimated_input_tokens_after_summary=primary_context.estimated_input_tokens_after_summary,
        estimated_input_tokens_after_prune=primary_context.estimated_input_tokens_after_prune,
        summary_triggered=primary_context.summary_triggered,
        prune_triggered=primary_context.prune_triggered,
        overflow_rejected=primary_context.overflow_rejected,
        output_reserve=primary_context.output_reserve,
        overhead_reserve=primary_context.overhead_reserve,
    )
    db.add(audit)

    for (
        usage_agent_id,
        usage_model_alias,
        usage_provider_model,
        usage_input_fresh,
        usage_input_cached,
        usage_output,
        usage_total,
    ) in state.usage_entries:
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
                agent_id=usage_agent_id,
            ),
        )
        debit_result = await wallet_service.stage_debit(
            db,
            user_id=user_id,
            credits_burned=credits_burned,
            reference_id=turn.id,
            note=f"turn:{turn.id}",
        )
        last_debit_balance = debit_result.new_balance

    for trace_agent, tool_calls in state.tool_trace_entries:
        for tool_call in tool_calls:
            db.add(
                ToolCallEvent(
                    id=str(uuid4()),
                    user_id=user_id,
                    room_id=session.room_id,
                    session_id=session.id,
                    turn_id=turn.id,
                    agent_key=trace_agent.agent_key,
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

    if last_debit_balance is None:
        balance_after = None
        low_balance = False
    else:
        balance_after = format_decimal(last_debit_balance)
        low_balance = last_debit_balance < Decimal(str(settings.low_balance_threshold))

    return TurnRead(
        id=turn.id,
        session_id=turn.session_id,
        turn_index=turn.turn_index,
        mode=turn.mode,
        user_input=turn.user_input,
        assistant_output=turn.assistant_output or "",
        status=turn.status,
        model_alias_used=model_alias_marker,
        summary_triggered=primary_context.summary_triggered,
        prune_triggered=primary_context.prune_triggered,
        overflow_rejected=False,
        balance_after=balance_after,
        low_balance=low_balance,
        summary_used_fallback=summary_used_fallback,
        created_at=turn.created_at,
    )


@router.post("/sessions/{session_id}/turns/stream")
async def create_turn_stream(
    session_id: str,
    payload: TurnCreateRequest,
    request: Request,
    current_user: dict[str, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    llm_gateway: LlmGateway = Depends(get_llm_gateway),
    usage_recorder: UsageRecorder = Depends(get_usage_recorder),
    wallet_service: WalletService = Depends(get_wallet_service),
    mode_executor: PurePythonModeExecutor = Depends(get_mode_executor),
) -> StreamingResponse:
    user_id = current_user["user_id"]
    settings = get_settings()
    await check_turn_rate_limit(user_id, getattr(request.app.state, "arq_redis", None), settings)
    session, room, standalone_agent = await _get_owned_active_session_or_404(
        db, session_id=session_id, user_id=user_id
    )

    room_agents: list[RoomAgent] = []
    selected_agents: list[ActiveAgent] = []
    active_agent: ActiveAgent | None = None
    turn_mode: str

    if room is not None:
        room_agents = (
            await db.scalars(
                select(RoomAgent)
                .options(selectinload(RoomAgent.agent))
                .join(Agent, Agent.id == RoomAgent.agent_id)
                .where(
                    RoomAgent.room_id == room.id,
                    Agent.deleted_at.is_(None),
                )
                .order_by(RoomAgent.position.asc(), RoomAgent.created_at.asc())
            )
        ).all()
        manual_tag_selected_agents: list[RoomAgent] = []
        tagged_keys = _extract_tagged_agent_keys(payload.message)
        by_key = {assignment.agent.agent_key.lower(): assignment for assignment in room_agents}
        manual_tag_selected_agents = [by_key[key] for key in tagged_keys if key in by_key]

        turn_mode = room.current_mode

        if manual_tag_selected_agents:
            # Explicitly tagged agents bypass current mode
            if len(manual_tag_selected_agents) > 1:
                turn_mode = "roundtable"
            else:
                turn_mode = "tag"
                
            active_room_agent = manual_tag_selected_agents[0]
            selected_assignments = manual_tag_selected_agents
        elif room.current_mode in {"manual", "tag"}:
            if not tagged_keys:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "no_valid_tagged_agents",
                        "message": "Manual mode requires at least one tagged agent (e.g., @writer).",
                    },
                )
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "no_valid_tagged_agents",
                    "message": "No tagged agents matched this room.",
                },
            )
        elif room.current_mode == "orchestrator":
            if not room_agents:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "no_room_agents",
                        "message": "Orchestrator mode requires at least one agent.",
                    },
                )
            active_room_agent = room_agents[0]
            selected_assignments = room_agents
        elif room.current_mode == "roundtable":
            if not room_agents:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "no_room_agents",
                        "message": "Round table mode requires at least one agent in the room.",
                    },
                )
            active_room_agent = room_agents[0]
            selected_assignments = room_agents
        else:
            selected_assignments = [active_room_agent] if active_room_agent is not None else []

        selected_agents = [_room_agent_to_selected_agent(assignment) for assignment in selected_assignments]
        active_agent = _room_agent_to_selected_agent(active_room_agent) if active_room_agent else None
    else:
        if standalone_agent is None:
            raise HTTPException(status_code=404, detail="Session not found.")
        active_agent = _standalone_agent_to_selected_agent(standalone_agent)
        selected_agents = [active_agent]
        turn_mode = "standalone"



    if get_enforcement_enabled(settings.credit_enforcement_enabled):
        wallet = await wallet_service.get_or_create_wallet(db, user_id=user_id)
        wallet_balance = wallet.balance if wallet.balance is not None else Decimal("0")
        if wallet_balance <= Decimal("0"):
            raise HTTPException(
                status_code=402,
                detail="Insufficient credits. Please top up your account.",
            )

    history_rows = (
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
    next_turn_index = int(await db.scalar(select(func.max(Turn.turn_index)).where(Turn.session_id == session.id)) or 0)
    context_manager = _build_context_manager()
    share_same_turn_outputs = turn_mode == "roundtable"

    def _build_history_messages_for_agent(current_agent_key: str | None) -> list[HistoryMessage]:
        if room is not None:
            shared = [item for item in history_rows if item.visibility == "shared"]
            private = [
                item
                for item in history_rows
                if item.visibility == "private" and item.agent_key == current_agent_key
            ]
            private_limit = max(settings.agent_private_context_turns_keep, 0) * 2
            if private_limit > 0 and len(private) > private_limit:
                private = private[-private_limit:]
            combined = sorted(shared + private, key=lambda item: (item.created_at, item.id))
        else:
            combined = [item for item in history_rows if item.visibility == "shared"]

        output: list[HistoryMessage] = []
        for message in combined:
            if message.role not in {"user", "assistant", "tool"}:
                continue
            role = "user" if message.role == "user" else "assistant"
            content = message.content
            if (
                room is not None
                and message.role == "assistant"
                and message.visibility == "shared"
                and current_agent_key is not None
                and message.source_agent_key is not None
                and message.source_agent_key != current_agent_key
            ):
                content = f"[{message.agent_name or message.source_agent_key}]: {message.content}"
            output.append(
                HistoryMessage(
                    id=message.id,
                    role=role,
                    content=content,
                    turn_id=message.turn_id,
                )
            )
        return output

    async def _stream_turn() -> AsyncIterator[str]:
        summary_used_fallback = False
        last_debit_balance: Decimal | None = None

        history_messages: list[HistoryMessage] = []
        if room is not None:
            combined = sorted(history_rows, key=lambda item: (item.created_at, item.id))
        else:
            combined = [item for item in history_rows if item.visibility == "shared"]

        for message in combined:
            if message.role not in {"user", "assistant", "tool"}:
                continue
            role = "user" if message.role == "user" else "assistant"
            
            # Sanitize assistant content by stripping legacy or hallucinated name tags
            content = message.content
            if message.role == "assistant":
                # Strip bracketed tags or leading name prefixes
                content = re.sub(r'^\[.*?\]:\s*', '', content)
                content = re.sub(r'^[A-Za-z0-9_\s]{2,20}:\s*', '', content)

            if room is not None and message.role == "assistant" and message.visibility == "shared":
                # Re-apply a standard, clean prefix for context
                content = f"{message.agent_name or message.source_agent_key}: {content}"
                
            history_messages.append(
                HistoryMessage(
                    id=message.id,
                    role=role,
                    content=content,
                    turn_id=message.turn_id,
                )
            )

        system_messages = []
        if room is not None:
            system_messages.append(ContextMessage(role="system", content=f"Room mode: {turn_mode}"))
            if room.goal:
                system_messages.append(ContextMessage(role="system", content=f"Room goal: {room.goal}"))
            
            files_result = await db.scalars(
                select(UploadedFile)
                .where(UploadedFile.room_id == room.id)
                .order_by(UploadedFile.created_at.desc())
            )
            files = files_result.all()
            if files:
                files_list = "\n".join(f"- {f.filename} (ID: {f.id})" for f in files)
                system_messages.append(ContextMessage(role="system", content=f"Available room files:\n{files_list}"))
        else:
            system_messages.append(ContextMessage(role="system", content="Session mode: standalone"))

        try:
            primary_context = context_manager.prepare(
                model_context_limit=settings.context_default_model_limit,
                system_messages=system_messages,
                history_messages=history_messages,
                latest_summary_text=latest_summary.summary_text if latest_summary else None,
                turn_count_since_last_summary=turn_count_since_summary,
                user_input=payload.message,
            )
        except ContextBudgetExceeded as exc:
            yield _sse_event({
                "type": "error", 
                "message": "Input exceeds session context budget. Shorten input or start a new session."
            })
            return

        import typing
        import asyncio
        
        state = TurnExecutionState(
            session_id=session.id,
            turn_index=next_turn_index + 1,
            user_input=payload.message,
            room_mode=typing.cast(typing.Any, turn_mode),
            active_agents=selected_agents,
            primary_context_messages=[GatewayMessage(role=m.role, content=m.content) for m in primary_context.messages],
            max_output_tokens=settings.context_max_output_tokens,
            room_id=session.room_id,
        )

        queue: asyncio.Queue[str | None] = asyncio.Queue()
        
        async def event_sink(event_type: str, data: dict) -> None:
            await queue.put(_sse_event({"type": event_type, **data}))
            
        async def run_executor():
            try:
                await mode_executor.run_turn(db, state, event_sink)
            except Exception as e:
                _LOGGER.error("Stream executor failed: %s", e)
            finally:
                await queue.put(None)
                
        executor_task = asyncio.create_task(run_executor())
        
        while True:
            item = await queue.get()
            if item is None:
                break
            yield item

        await executor_task

        model_alias = selected_agents[0].model_alias if selected_agents else "fake"
        model_alias_for_marker = model_alias
        if turn_mode == "orchestrator" and state.usage_entries:
            model_alias_for_marker = state.usage_entries[0][1]
        multi_agent_mode = state.total_invocations > 1 if turn_mode == "orchestrator" else len(selected_agents) > 1
        model_alias_marker = (
            "roundtable"
            if turn_mode == "roundtable"
            else ("multi-agent" if turn_mode == "orchestrator" and multi_agent_mode else model_alias_for_marker)
        )

        if turn_mode == "orchestrator" and state.per_round_entries:
            if len(state.per_round_entries) > 1:
                round_blocks: list[str] = []
                for round_idx, round_entries in enumerate(state.per_round_entries, start=1):
                    lines = [f"[Round {round_idx}]"]
                    lines.extend(f"{entry_agent.name}: {content}" for entry_agent, content in round_entries)
                    round_blocks.append("\n".join(lines))
                assistant_output_text = "\n\n".join(round_blocks)
            else:
                single_round = state.per_round_entries[0]
                assistant_output_text = (
                    "\n\n".join(f"{entry_agent.name}: {content}" for entry_agent, content in single_round)
                    if len(single_round) > 1
                    else (single_round[0][1] if single_round else "")
                )
        else:
            assistant_output_text = (
                "\n\n".join([f"{entry_agent.name}: {content}" for entry_agent, content in state.assistant_entries])
                if multi_agent_mode
                else (state.assistant_entries[0][1] if state.assistant_entries else "")
            )
        if state.final_synthesis:
            synthesis_block = f"Manager synthesis:\n{state.final_synthesis}"
            assistant_output_text = (
                f"{assistant_output_text}\n\n---\n\n{synthesis_block}" if assistant_output_text else synthesis_block
            )

        turn = Turn(
            id=str(uuid4()),
            session_id=session.id,
            turn_index=next_turn_index + 1,
            mode=turn_mode,
            user_input=payload.message,
            assistant_output=assistant_output_text,
            status=state.current_status,
        )
        db.add(turn)
        await db.flush()

        base_msg_time = turn.created_at
        if base_msg_time is None:
            await db.refresh(turn, ["created_at"])
            base_msg_time = turn.created_at

        db.add(
            Message(
                id=str(uuid4()),
                turn_id=turn.id,
                session_id=session.id,
                role="user",
                visibility="shared",
                agent_key=None,
                source_agent_key=None,
                agent_name=None,
                mode=turn_mode,
                content=payload.message,
                created_at=base_msg_time,
            )
        )
        for trace_agent, tool_calls in state.tool_trace_entries:
            for tool_call in tool_calls:
                db.add(
                    Message(
                        id=str(uuid4()),
                        turn_id=turn.id,
                        session_id=session.id,
                        role="assistant",
                        visibility="private",
                        agent_key=trace_agent.agent_key,
                        source_agent_key=trace_agent.agent_key,
                        agent_name=trace_agent.name,
                        mode=turn_mode,
                        content=f"Tool Call: {tool_call.tool_name}({tool_call.input_json}) -> {tool_call.output_json}",
                        created_at=base_msg_time,
                    )
                )

        for i, (entry_agent, entry_content) in enumerate(state.assistant_entries, start=1):
            db.add(
                Message(
                    id=str(uuid4()),
                    turn_id=turn.id,
                    session_id=session.id,
                    role="assistant",
                    visibility="shared",
                    agent_key=entry_agent.agent_key,
                    source_agent_key=entry_agent.agent_key,
                    agent_name=entry_agent.name,
                    mode=turn_mode,
                    content=entry_content,
                    created_at=base_msg_time + timedelta(milliseconds=i),
                )
            )

        if state.final_synthesis:
            db.add(
                Message(
                    id=str(uuid4()),
                    turn_id=turn.id,
                    session_id=session.id,
                    role="assistant",
                    visibility="shared",
                    agent_key="manager",
                    source_agent_key="manager",
                    agent_name="Manager",
                    mode=turn_mode,
                    content=state.final_synthesis,
                    created_at=base_msg_time + timedelta(milliseconds=len(state.assistant_entries) + 1),
                )
            )

        if primary_context.summary_triggered:
            from arq import ArqRedis
            redis_pool: ArqRedis | None = getattr(request.app.state, "arq_redis", None)
            if redis_pool:
                await redis_pool.enqueue_job(
                    "session_summary",
                    session.id,
                    primary_context.summary_from_message_id,
                    primary_context.summary_to_message_id,
                )
            else:
                _LOGGER.warning("arq_redis not found in app state; skipping async summarization for session %s", session.id)

        db.add(
            TurnContextAudit(
                id=str(uuid4()),
                turn_id=turn.id,
                session_id=session.id,
                model_alias=model_alias_marker,
                model_context_limit=primary_context.model_context_limit,
                input_budget=primary_context.input_budget,
                estimated_input_tokens_before=primary_context.estimated_input_tokens_before,
                estimated_input_tokens_after_summary=primary_context.estimated_input_tokens_after_summary,
                estimated_input_tokens_after_prune=primary_context.estimated_input_tokens_after_prune,
                summary_triggered=primary_context.summary_triggered,
                prune_triggered=primary_context.prune_triggered,
                overflow_rejected=primary_context.overflow_rejected,
                output_reserve=primary_context.output_reserve,
                overhead_reserve=primary_context.overhead_reserve,
            )
        )

        for (
            usage_agent_id,
            usage_model_alias,
            usage_provider_model,
            usage_input_fresh,
            usage_input_cached,
            usage_output,
            usage_total,
        ) in state.usage_entries:
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
                    agent_id=usage_agent_id,
                ),
            )
            debit_result = await wallet_service.stage_debit(
                db,
                user_id=user_id,
                credits_burned=credits_burned,
                reference_id=turn.id,
                note=f"turn:{turn.id}",
            )
            last_debit_balance = debit_result.new_balance

        await db.commit()
        await db.refresh(turn)

        done_payload: dict[str, object] = {
            "type": "done",
            "turn_id": turn.id,
            "provider_model": state.usage_entries[-1][2] if state.usage_entries else (active_agent.model_alias if active_agent else "unknown"),
            "summary_used_fallback": summary_used_fallback,
        }
        if last_debit_balance is not None:
            done_payload["balance_after"] = format_decimal(last_debit_balance)
            done_payload["low_balance"] = last_debit_balance < Decimal(str(settings.low_balance_threshold))
        yield _sse_event(done_payload)

    return StreamingResponse(
        _stream_turn(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
