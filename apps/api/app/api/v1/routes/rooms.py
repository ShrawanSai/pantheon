from __future__ import annotations

from datetime import datetime, timezone
import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.db.models import Agent, Room, RoomAgent, User
from apps.api.app.db.session import get_db
from apps.api.app.dependencies.auth import get_current_user
from apps.api.app.dependencies.rooms import get_owned_active_room_or_404
from apps.api.app.schemas.agents import AgentRead
from apps.api.app.schemas.rooms import (
    RoomAgentCreateRequest,
    RoomAgentRead,
    RoomCreateRequest,
    RoomModeUpdateRequest,
    RoomRead,
)

router = APIRouter(prefix="/rooms", tags=["rooms"])


def _room_to_read(room: Room) -> RoomRead:
    return RoomRead(
        id=room.id,
        owner_user_id=room.owner_user_id,
        name=room.name,
        goal=room.goal,
        current_mode=room.current_mode,
        pending_mode=room.pending_mode,
        created_at=room.created_at,
        updated_at=room.updated_at,
    )


def _agent_model_to_read(agent: Agent) -> AgentRead:
    try:
        tool_permissions = json.loads(agent.tool_permissions_json)
    except json.JSONDecodeError:
        tool_permissions = []
    if not isinstance(tool_permissions, list):
        tool_permissions = []
    return AgentRead(
        id=agent.id,
        owner_user_id=agent.owner_user_id,
        agent_key=agent.agent_key,
        name=agent.name,
        model_alias=agent.model_alias,
        role_prompt=agent.role_prompt,
        tool_permissions=[str(item) for item in tool_permissions],
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


def _assignment_to_read(assignment: RoomAgent) -> RoomAgentRead:
    if assignment.agent is None:
        raise ValueError("RoomAgent assignment missing linked agent.")
    agent_for_read = _agent_model_to_read(assignment.agent)
    return RoomAgentRead(
        id=assignment.id,
        room_id=assignment.room_id,
        agent_id=assignment.agent_id,
        agent=agent_for_read,
        position=assignment.position,
        created_at=assignment.created_at,
    )


@router.post("", response_model=RoomRead, status_code=status.HTTP_201_CREATED)
async def create_room(
    payload: RoomCreateRequest,
    current_user: dict[str, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RoomRead:
    user_id = current_user["user_id"]
    email = (current_user.get("email") or "").strip() or f"{user_id}@placeholder.local"

    existing_user = await db.get(User, user_id)
    if existing_user is None:
        db.add(User(id=user_id, email=email))

    room = Room(
        id=str(uuid4()),
        owner_user_id=user_id,
        name=payload.name.strip(),
        goal=payload.goal,
        current_mode=payload.current_mode,
        pending_mode=None,
    )
    db.add(room)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Room creation conflicted with existing data.") from exc

    await db.refresh(room)
    return _room_to_read(room)


@router.get("", response_model=list[RoomRead])
async def list_rooms(
    current_user: dict[str, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[RoomRead]:
    user_id = current_user["user_id"]
    result = await db.scalars(
        select(Room)
        .where(
            Room.owner_user_id == user_id,
            Room.deleted_at.is_(None),
        )
        .order_by(Room.created_at.desc())
    )
    return [_room_to_read(room) for room in result.all()]


@router.get("/{room_id}", response_model=RoomRead)
async def get_room(
    room_id: str,
    current_user: dict[str, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RoomRead:
    user_id = current_user["user_id"]
    room = await get_owned_active_room_or_404(db, room_id=room_id, user_id=user_id)
    return _room_to_read(room)


@router.delete("/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_room(
    room_id: str,
    current_user: dict[str, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    user_id = current_user["user_id"]
    room = await get_owned_active_room_or_404(db, room_id=room_id, user_id=user_id)

    room.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/{room_id}/mode", response_model=RoomRead)
async def patch_room_mode(
    room_id: str,
    payload: RoomModeUpdateRequest,
    current_user: dict[str, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RoomRead:
    user_id = current_user["user_id"]
    room = await get_owned_active_room_or_404(db, room_id=room_id, user_id=user_id)

    requested_mode = payload.mode.strip().lower()
    if requested_mode not in {"manual", "roundtable", "orchestrator"}:
        raise HTTPException(
            status_code=422,
            detail="unsupported mode; allowed: manual, roundtable, orchestrator",
        )

    room.current_mode = requested_mode
    room.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(room)
    return _room_to_read(room)


@router.post("/{room_id}/agents", response_model=RoomAgentRead, status_code=status.HTTP_201_CREATED)
async def create_room_agent(
    room_id: str,
    payload: RoomAgentCreateRequest,
    current_user: dict[str, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RoomAgentRead:
    user_id = current_user["user_id"]
    await get_owned_active_room_or_404(db, room_id=room_id, user_id=user_id)
    agent = await db.scalar(
        select(Agent).where(
            Agent.id == payload.agent_id,
            Agent.owner_user_id == user_id,
            Agent.deleted_at.is_(None),
        )
    )
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found.")

    if payload.position is None:
        max_position = await db.scalar(select(func.max(RoomAgent.position)).where(RoomAgent.room_id == room_id))
        position = (max_position or 0) + 1
    else:
        position = payload.position

    assignment = RoomAgent(
        id=str(uuid4()),
        room_id=room_id,
        agent_id=payload.agent_id,
        position=position,
    )
    db.add(assignment)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Agent already assigned to this room.") from exc

    stored_assignment = await db.scalar(
        select(RoomAgent)
        .options(selectinload(RoomAgent.agent))
        .where(RoomAgent.id == assignment.id)
    )
    if stored_assignment is None:
        raise HTTPException(status_code=500, detail="Failed to load created room assignment.")
    return _assignment_to_read(stored_assignment)


@router.get("/{room_id}/agents", response_model=list[RoomAgentRead])
async def list_room_agents(
    room_id: str,
    current_user: dict[str, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[RoomAgentRead]:
    user_id = current_user["user_id"]
    await get_owned_active_room_or_404(db, room_id=room_id, user_id=user_id)

    result = await db.scalars(
        select(RoomAgent)
        .options(selectinload(RoomAgent.agent))
        .join(Agent, Agent.id == RoomAgent.agent_id)
        .where(
            RoomAgent.room_id == room_id,
            Agent.deleted_at.is_(None),
        )
        .order_by(RoomAgent.position.asc(), RoomAgent.created_at.asc())
    )
    return [_assignment_to_read(agent) for agent in result.all()]


@router.delete("/{room_id}/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_room_agent(
    room_id: str,
    agent_id: str,
    current_user: dict[str, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    user_id = current_user["user_id"]
    await get_owned_active_room_or_404(db, room_id=room_id, user_id=user_id)

    agent = await db.scalar(
        select(RoomAgent).where(
            RoomAgent.room_id == room_id,
            RoomAgent.agent_id == agent_id,
        )
    )
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found.")

    await db.delete(agent)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
