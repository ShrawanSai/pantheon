from __future__ import annotations

from dataclasses import dataclass
import json
from collections.abc import AsyncIterator
from decimal import Decimal
import logging
import re
import time
from datetime import datetime, timezone
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
    ToolCallRecord,
    TurnExecutor,
    TurnExecutionInput,
    get_mode_executor,
)
from apps.api.app.services.orchestration.orchestrator_manager import (
    build_orchestrator_synthesis_messages,
    generate_orchestrator_synthesis,
    route_turn,
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


@dataclass(frozen=True)
class _SelectedAgent:
    agent_id: str | None
    agent_key: str | None
    name: str
    model_alias: str
    role_prompt: str
    tool_permissions: tuple[str, ...]


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


def _room_agent_to_selected_agent(room_agent: RoomAgent) -> _SelectedAgent:
    if room_agent.agent is None:
        raise HTTPException(status_code=500, detail="Room agent assignment missing linked agent.")
    linked = room_agent.agent
    return _SelectedAgent(
        agent_id=linked.id,
        agent_key=linked.agent_key,
        name=linked.name,
        model_alias=linked.model_alias,
        role_prompt=linked.role_prompt,
        tool_permissions=tuple(get_permitted_tool_names(linked)),
    )


def _standalone_agent_to_selected_agent(agent: Agent) -> _SelectedAgent:
    return _SelectedAgent(
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
    rows = await db.scalars(
        select(Message)
        .where(*conditions)
        .order_by(
            Message.created_at.asc(),
            case((Message.role == "user", 0), else_=1).asc(),
            Message.id.asc(),
        )
        .limit(limit)
        .offset(offset)
    )
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
            for row in rows.all()
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
    selected_agents: list[_SelectedAgent] = []
    active_agent: _SelectedAgent | None = None
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
        active_room_agent = room_agents[0] if room_agents else None
        manual_tag_selected_agents: list[RoomAgent] = []
        orchestrator_selected_agents: list[RoomAgent] = []

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
            by_key = {assignment.agent.agent_key.lower(): assignment for assignment in room_agents}
            manual_tag_selected_agents = [by_key[key] for key in tagged_keys if key in by_key]
            if not manual_tag_selected_agents:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "no_valid_tagged_agents",
                        "message": "No tagged agents matched this room.",
                    },
                )
            active_room_agent = manual_tag_selected_agents[0]
        elif room.current_mode == "orchestrator":
            if not room_agents:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "no_room_agents",
                        "message": "Orchestrator mode requires at least one agent.",
                    },
                )
            decision = await route_turn(
                agents=[assignment.agent for assignment in room_agents],
                user_input=payload.message,
                gateway=llm_gateway,
                manager_model_alias=settings.orchestrator_manager_model_alias,
            )
            by_key = {assignment.agent.agent_key.lower(): assignment for assignment in room_agents}
            orchestrator_selected_agents = [
                by_key[key.lower()] for key in decision.selected_agent_keys if key.lower() in by_key
            ]
            if not orchestrator_selected_agents:
                orchestrator_selected_agents = [room_agents[0]]
            active_room_agent = orchestrator_selected_agents[0]
        if room.current_mode == "roundtable" and not room_agents:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "no_room_agents",
                    "message": "Round table mode requires at least one agent in the room.",
                },
            )

        if room.current_mode == "roundtable":
            selected_assignments = room_agents
        elif room.current_mode == "orchestrator":
            selected_assignments = orchestrator_selected_agents or (
                [active_room_agent] if active_room_agent is not None else []
            )
        elif room.current_mode in {"manual", "tag"}:
            selected_assignments = manual_tag_selected_agents or (
                [active_room_agent] if active_room_agent is not None else []
            )
        else:
            selected_assignments = [active_room_agent] if active_room_agent is not None else []
        if room.current_mode == "orchestrator" and len(selected_assignments) > 3:
            _LOGGER.warning(
                "Orchestrator selected %d agents; truncating to 3 per MVP cap.",
                len(selected_assignments),
            )
            selected_assignments = selected_assignments[:3]

        selected_agents = [_room_agent_to_selected_agent(assignment) for assignment in selected_assignments]
        active_agent = _room_agent_to_selected_agent(active_room_agent) if active_room_agent else None
        turn_mode = room.current_mode
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

    share_same_turn_outputs = turn_mode in {"roundtable", "orchestrator"}
    prior_roundtable_outputs: list[GatewayMessage] = []
    assistant_entries: list[tuple[_SelectedAgent, str]] = []
    usage_entries: list[tuple[str | None, str, str, int, int, int, int]] = []
    tool_event_entries: list[tuple[str | None, tuple[ToolCallRecord, ...]]] = []
    tool_trace_entries: list[tuple[_SelectedAgent, tuple[ToolCallRecord, ...]]] = []
    turn_status = "completed"
    last_debit_balance: Decimal | None = None
    summary_used_fallback = False
    primary_context = None

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

    for selected_agent in selected_agents:
        if selected_agent is None:
            continue

        selected_agent_name = selected_agent.name
        selected_agent_alias = payload.model_alias_override or selected_agent.model_alias
        selected_agent_role = selected_agent.role_prompt
        selected_agent_id = selected_agent.agent_id
        selected_agent_key = selected_agent.agent_key
        selected_agent_tools = selected_agent.tool_permissions

        if room is not None and turn_mode == "roundtable":
            system_messages = [
                ContextMessage(role="system", content=f"Room mode: {turn_mode}"),
                ContextMessage(role="system", content=f"Room goal: {room.goal or 'No goal specified.'}"),
            ]
        elif room is not None:
            system_messages = [
                ContextMessage(role="system", content=f"Room mode: {turn_mode}"),
                ContextMessage(role="system", content=f"Room goal: {room.goal or 'No goal specified.'}"),
                ContextMessage(role="system", content=f"Agent role: {selected_agent_role}"),
            ]
        else:
            system_messages = [
                ContextMessage(role="system", content="Session mode: standalone"),
                ContextMessage(role="system", content=f"Agent role: {selected_agent_role}"),
            ]

        history_messages = _build_history_messages_for_agent(selected_agent_key)

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

        if primary_context is None:
            primary_context = context

        request_messages: list[GatewayMessage] = [
            GatewayMessage(role="system", content=f"Agent role: {selected_agent_role}"),
            *[GatewayMessage(role=item.role, content=item.content) for item in context.messages],
            *prior_roundtable_outputs,
        ]
        allowed_tools = selected_agent_tools

        try:
            gateway_response = await mode_executor.run_turn(
                db,
                TurnExecutionInput(
                    model_alias=selected_agent_alias,
                    messages=request_messages,
                    max_output_tokens=settings.context_max_output_tokens,
                    thread_id=f"{session.id}:{next_turn_index + 1}:{selected_agent_name}",
                    allowed_tool_names=allowed_tools,
                    room_id=session.room_id or "",
                ),
            )
            assistant_entries.append((selected_agent, gateway_response.text))
            usage_entries.append(
                (
                    selected_agent_id,
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
                    selected_agent_key,
                    gateway_response.tool_calls,
                )
            )
            tool_trace_entries.append((selected_agent, gateway_response.tool_calls))
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
            assistant_entries.append((selected_agent, error_content))
            if share_same_turn_outputs:
                prior_roundtable_outputs.append(
                    GatewayMessage(role="assistant", content=f"{selected_agent_name}: {error_content}")
                )

    if primary_context is None:
        raise HTTPException(status_code=422, detail="No executable agent found for this turn.")

    manager_synthesis_text: str | None = None
    if turn_mode == "orchestrator":
        specialist_outputs = [
            (entry_agent.name, entry_content)
            for entry_agent, entry_content in assistant_entries
            if not entry_content.startswith("[[agent_error]]")
        ]
        if specialist_outputs:
            try:
                synthesis_result = await generate_orchestrator_synthesis(
                    gateway=llm_gateway,
                    manager_model_alias=settings.orchestrator_manager_model_alias,
                    user_input=payload.message,
                    specialist_outputs=specialist_outputs,
                    max_output_tokens=settings.context_max_output_tokens,
                )
                if synthesis_result is not None:
                    manager_synthesis_text = synthesis_result.text.strip()
                    usage_entries.append(
                        (
                            None,
                            settings.orchestrator_manager_model_alias,
                            synthesis_result.response.provider_model,
                            synthesis_result.response.usage.input_tokens_fresh,
                            synthesis_result.response.usage.input_tokens_cached,
                            synthesis_result.response.usage.output_tokens,
                            synthesis_result.response.usage.total_tokens,
                        )
                    )
            except Exception as exc:
                turn_status = "partial"
                _LOGGER.warning("Orchestrator synthesis failed for session %s: %s", session.id, exc)
                manager_synthesis_text = (
                    f"[[manager_synthesis_error]] type={exc.__class__.__name__} "
                    f"message={str(exc) or 'synthesis_failed'}"
                )
        else:
            _LOGGER.info("Skipping orchestrator synthesis for session %s: no specialist outputs.", session.id)

    multi_agent_mode = len(selected_agents) > 1
    model_alias_marker = (
        "roundtable"
        if turn_mode == "roundtable"
        else ("multi-agent" if turn_mode == "orchestrator" and multi_agent_mode else model_alias)
    )
    assistant_output_text = (
        "\n\n".join([f"{entry_agent.name}: {content}" for entry_agent, content in assistant_entries])
        if multi_agent_mode
        else (assistant_entries[0][1] if assistant_entries else "")
    )
    if manager_synthesis_text:
        synthesis_block = f"Manager synthesis:\n{manager_synthesis_text}"
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
        visibility="shared",
        agent_key=None,
        source_agent_key=None,
        agent_name=None,
        mode=turn_mode,
        content=payload.message,
    )
    db.add(user_message)
    for trace_agent, tool_calls in tool_trace_entries:
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

    for entry_agent, entry_content in assistant_entries:
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
    if manager_synthesis_text:
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
                content=manager_synthesis_text,
            )
        )

    if primary_context.generated_summary_text:
        generated = await generate_summary_text(
            raw_summary_text=primary_context.generated_summary_text,
            gateway=llm_gateway,
            model_alias=settings.summarizer_model_alias,
        )
        summary_used_fallback = generated.used_fallback
        structure = await extract_summary_structure(
            summary_text=generated.summary_text,
            gateway=llm_gateway,
            model_alias=settings.summarizer_model_alias,
        )
        summary = SessionSummary(
            id=str(uuid4()),
            session_id=session.id,
            from_message_id=primary_context.summary_from_message_id,
            to_message_id=primary_context.summary_to_message_id,
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
) -> StreamingResponse:
    user_id = current_user["user_id"]
    settings = get_settings()
    await check_turn_rate_limit(user_id, getattr(request.app.state, "arq_redis", None), settings)
    session, room, standalone_agent = await _get_owned_active_session_or_404(
        db, session_id=session_id, user_id=user_id
    )

    room_agents: list[RoomAgent] = []
    selected_agents: list[_SelectedAgent] = []
    active_agent: _SelectedAgent | None = None
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
        active_room_agent = room_agents[0] if room_agents else None
        manual_tag_selected_agents: list[RoomAgent] = []
        orchestrator_selected_agents: list[RoomAgent] = []

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
            by_key = {assignment.agent.agent_key.lower(): assignment for assignment in room_agents}
            manual_tag_selected_agents = [by_key[key] for key in tagged_keys if key in by_key]
            if not manual_tag_selected_agents:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "no_valid_tagged_agents",
                        "message": "No tagged agents matched this room.",
                    },
                )
            active_room_agent = manual_tag_selected_agents[0]
        elif room.current_mode == "orchestrator":
            if not room_agents:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "no_room_agents",
                        "message": "Orchestrator mode requires at least one agent.",
                    },
                )
            decision = await route_turn(
                agents=[assignment.agent for assignment in room_agents],
                user_input=payload.message,
                gateway=llm_gateway,
                manager_model_alias=settings.orchestrator_manager_model_alias,
            )
            by_key = {assignment.agent.agent_key.lower(): assignment for assignment in room_agents}
            orchestrator_selected_agents = [
                by_key[key.lower()] for key in decision.selected_agent_keys if key.lower() in by_key
            ]
            if not orchestrator_selected_agents:
                orchestrator_selected_agents = [room_agents[0]]
            active_room_agent = orchestrator_selected_agents[0]
        if room.current_mode == "roundtable" and not room_agents:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "no_room_agents",
                    "message": "Round table mode requires at least one agent in the room.",
                },
            )

        if room.current_mode == "roundtable":
            selected_assignments = room_agents
        elif room.current_mode == "orchestrator":
            selected_assignments = orchestrator_selected_agents or (
                [active_room_agent] if active_room_agent is not None else []
            )
        elif room.current_mode in {"manual", "tag"}:
            selected_assignments = manual_tag_selected_agents or (
                [active_room_agent] if active_room_agent is not None else []
            )
        else:
            selected_assignments = [active_room_agent] if active_room_agent is not None else []
        if room.current_mode == "orchestrator" and len(selected_assignments) > 3:
            _LOGGER.warning(
                "Orchestrator selected %d agents; truncating to 3 per MVP cap.",
                len(selected_assignments),
            )
            selected_assignments = selected_assignments[:3]

        selected_agents = [_room_agent_to_selected_agent(assignment) for assignment in selected_assignments]
        active_agent = _room_agent_to_selected_agent(active_room_agent) if active_room_agent else None
        turn_mode = room.current_mode
    else:
        if standalone_agent is None:
            raise HTTPException(status_code=404, detail="Session not found.")
        active_agent = _standalone_agent_to_selected_agent(standalone_agent)
        selected_agents = [active_agent]
        turn_mode = "standalone"

    if any(agent.tool_permissions for agent in selected_agents):
        raise HTTPException(status_code=422, detail="streaming not supported when tools are enabled")

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
    share_same_turn_outputs = turn_mode in {"roundtable", "orchestrator"}

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
        prior_roundtable_outputs: list[GatewayMessage] = []
        assistant_entries: list[tuple[_SelectedAgent, str]] = []
        usage_entries: list[tuple[str | None, str, str, int, int, int, int]] = []
        turn_status = "completed"
        primary_context = None
        summary_used_fallback = False
        last_debit_balance: Decimal | None = None
        manager_synthesis_text: str | None = None

        for selected_agent in selected_agents:
            selected_agent_name = selected_agent.name
            selected_agent_alias = payload.model_alias_override or selected_agent.model_alias
            selected_agent_role = selected_agent.role_prompt
            selected_agent_id = selected_agent.agent_id
            selected_agent_key = selected_agent.agent_key

            if room is not None and turn_mode == "roundtable":
                system_messages = [
                    ContextMessage(role="system", content=f"Room mode: {turn_mode}"),
                    ContextMessage(role="system", content=f"Room goal: {room.goal or 'No goal specified.'}"),
                ]
            elif room is not None:
                system_messages = [
                    ContextMessage(role="system", content=f"Room mode: {turn_mode}"),
                    ContextMessage(role="system", content=f"Room goal: {room.goal or 'No goal specified.'}"),
                    ContextMessage(role="system", content=f"Agent role: {selected_agent_role}"),
                ]
            else:
                system_messages = [
                    ContextMessage(role="system", content="Session mode: standalone"),
                    ContextMessage(role="system", content=f"Agent role: {selected_agent_role}"),
                ]

            history_messages = _build_history_messages_for_agent(selected_agent_key)
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

            if primary_context is None:
                primary_context = context

            request_messages: list[GatewayMessage] = [
                GatewayMessage(role="system", content=f"Agent role: {selected_agent_role}"),
                *[GatewayMessage(role=item.role, content=item.content) for item in context.messages],
                *prior_roundtable_outputs,
            ]
            output_parts: list[str] = []

            try:
                stream_ctx: StreamingContext = await llm_gateway.stream(
                    GatewayRequest(
                        model_alias=selected_agent_alias,
                        messages=request_messages,
                        max_output_tokens=settings.context_max_output_tokens,
                    )
                )
                if len(selected_agents) > 1:
                    prefix = f"{selected_agent_name}: "
                    yield _sse_event({"type": "chunk", "delta": prefix})
                async for delta in stream_ctx.chunks:
                    output_parts.append(delta)
                    yield _sse_event({"type": "chunk", "delta": delta})

                streamed_text = "".join(output_parts)
                usage = await stream_ctx.usage_future
                provider_model = await stream_ctx.provider_model_future

                assistant_entries.append((selected_agent, streamed_text))
                usage_entries.append(
                    (
                        selected_agent_id,
                        selected_agent_alias,
                        provider_model,
                        usage.input_tokens_fresh,
                        usage.input_tokens_cached,
                        usage.output_tokens,
                        usage.total_tokens,
                    )
                )
                if share_same_turn_outputs:
                    prior_roundtable_outputs.append(
                        GatewayMessage(role="assistant", content=f"{selected_agent_name}: {streamed_text}")
                    )
            except Exception as exc:
                turn_status = "partial"
                error_content = (
                    f"[[agent_error]] agent={selected_agent_name} "
                    f"type={exc.__class__.__name__} message={str(exc) or 'execution_failed'}"
                )
                assistant_entries.append((selected_agent, error_content))
                yield _sse_event({"type": "chunk", "delta": f"{selected_agent_name}: {error_content}"})
                if share_same_turn_outputs:
                    prior_roundtable_outputs.append(
                        GatewayMessage(role="assistant", content=f"{selected_agent_name}: {error_content}")
                    )

        if primary_context is None:
            raise HTTPException(status_code=422, detail="No executable agent found for this turn.")

        if turn_mode == "orchestrator":
            specialist_outputs = [
                (entry_agent.name, entry_content)
                for entry_agent, entry_content in assistant_entries
                if not entry_content.startswith("[[agent_error]]")
            ]
            if specialist_outputs:
                yield _sse_event({"type": "chunk", "delta": "\n\n---\n\nManager synthesis:\n"})
                try:
                    synthesis_stream = await llm_gateway.stream(
                        GatewayRequest(
                            model_alias=settings.orchestrator_manager_model_alias,
                            messages=build_orchestrator_synthesis_messages(
                                user_input=payload.message,
                                specialist_outputs=specialist_outputs,
                            ),
                            max_output_tokens=settings.context_max_output_tokens,
                        )
                    )
                    synthesis_parts: list[str] = []
                    async for delta in synthesis_stream.chunks:
                        synthesis_parts.append(delta)
                        yield _sse_event({"type": "chunk", "delta": delta})

                    manager_synthesis_text = "".join(synthesis_parts).strip()
                    synthesis_usage = await synthesis_stream.usage_future
                    synthesis_provider_model = await synthesis_stream.provider_model_future
                    usage_entries.append(
                        (
                            None,
                            settings.orchestrator_manager_model_alias,
                            synthesis_provider_model,
                            synthesis_usage.input_tokens_fresh,
                            synthesis_usage.input_tokens_cached,
                            synthesis_usage.output_tokens,
                            synthesis_usage.total_tokens,
                        )
                    )
                except Exception as exc:
                    turn_status = "partial"
                    _LOGGER.warning("Orchestrator synthesis stream failed for session %s: %s", session.id, exc)
                    manager_synthesis_text = (
                        f"[[manager_synthesis_error]] type={exc.__class__.__name__} "
                        f"message={str(exc) or 'synthesis_failed'}"
                    )
                    yield _sse_event({"type": "chunk", "delta": manager_synthesis_text})
            else:
                _LOGGER.info("Skipping orchestrator synthesis for session %s: no specialist outputs.", session.id)

        model_alias = payload.model_alias_override or (active_agent.model_alias if active_agent else "deepseek")
        multi_agent_mode = len(selected_agents) > 1
        model_alias_marker = (
            "roundtable"
            if turn_mode == "roundtable"
            else ("multi-agent" if turn_mode == "orchestrator" and multi_agent_mode else model_alias)
        )
        assistant_output_text = (
            "\n\n".join([f"{entry_agent.name}: {content}" for entry_agent, content in assistant_entries])
            if multi_agent_mode
            else (assistant_entries[0][1] if assistant_entries else "")
        )
        if manager_synthesis_text:
            synthesis_block = f"Manager synthesis:\n{manager_synthesis_text}"
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
            status=turn_status,
        )
        db.add(turn)
        await db.flush()

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
            )
        )
        for entry_agent, entry_content in assistant_entries:
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
        if manager_synthesis_text:
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
                    content=manager_synthesis_text,
                )
            )

        if primary_context.generated_summary_text:
            generated = await generate_summary_text(
                raw_summary_text=primary_context.generated_summary_text,
                gateway=llm_gateway,
                model_alias=settings.summarizer_model_alias,
            )
            summary_used_fallback = generated.used_fallback
            structure = await extract_summary_structure(
                summary_text=generated.summary_text,
                gateway=llm_gateway,
                model_alias=settings.summarizer_model_alias,
            )
            db.add(
                SessionSummary(
                    id=str(uuid4()),
                    session_id=session.id,
                    from_message_id=primary_context.summary_from_message_id,
                    to_message_id=primary_context.summary_to_message_id,
                    summary_text=generated.summary_text,
                    key_facts_json=json.dumps(structure.key_facts),
                    open_questions_json=json.dumps(structure.open_questions),
                    decisions_json=json.dumps(structure.decisions),
                    action_items_json=json.dumps(structure.action_items),
                )
            )

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
            "provider_model": usage_entries[-1][2] if usage_entries else (active_agent.model_alias if active_agent else "unknown"),
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
