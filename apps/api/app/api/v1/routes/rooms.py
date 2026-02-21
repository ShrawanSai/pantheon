from __future__ import annotations

from datetime import datetime
import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.db.models import Room, RoomAgent, User
from apps.api.app.db.session import get_db
from apps.api.app.dependencies.auth import get_current_user
from apps.api.app.schemas.rooms import (
    RoomAgentCreateRequest,
    RoomAgentRead,
    RoomCreateRequest,
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


def _agent_to_read(agent: RoomAgent) -> RoomAgentRead:
    try:
        tool_permissions = json.loads(agent.tool_permissions_json)
    except json.JSONDecodeError:
        tool_permissions = []
    if not isinstance(tool_permissions, list):
        tool_permissions = []
    return RoomAgentRead(
        id=agent.id,
        room_id=agent.room_id,
        agent_key=agent.agent_key,
        name=agent.name,
        model_alias=agent.model_alias,
        role_prompt=agent.role_prompt,
        tool_permissions=[str(item) for item in tool_permissions],
        position=agent.position,
        created_at=agent.created_at,
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
    room = await _get_owned_active_room_or_404(db, room_id=room_id, user_id=user_id)
    return _room_to_read(room)


@router.delete("/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_room(
    room_id: str,
    current_user: dict[str, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    user_id = current_user["user_id"]
    room = await _get_owned_active_room_or_404(db, room_id=room_id, user_id=user_id)

    room.deleted_at = datetime.now()
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{room_id}/agents", response_model=RoomAgentRead, status_code=status.HTTP_201_CREATED)
async def create_room_agent(
    room_id: str,
    payload: RoomAgentCreateRequest,
    current_user: dict[str, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RoomAgentRead:
    user_id = current_user["user_id"]
    await _get_owned_active_room_or_404(db, room_id=room_id, user_id=user_id)

    if payload.position is None:
        max_position = await db.scalar(select(func.max(RoomAgent.position)).where(RoomAgent.room_id == room_id))
        position = (max_position or 0) + 1
    else:
        position = payload.position

    agent = RoomAgent(
        id=str(uuid4()),
        room_id=room_id,
        agent_key=payload.agent_key,
        name=payload.name,
        model_alias=payload.model_alias,
        role_prompt=payload.role_prompt,
        tool_permissions_json=json.dumps(payload.tool_permissions),
        position=position,
    )
    db.add(agent)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Agent key already exists in this room.") from exc

    await db.refresh(agent)
    return _agent_to_read(agent)


@router.get("/{room_id}/agents", response_model=list[RoomAgentRead])
async def list_room_agents(
    room_id: str,
    current_user: dict[str, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[RoomAgentRead]:
    user_id = current_user["user_id"]
    await _get_owned_active_room_or_404(db, room_id=room_id, user_id=user_id)

    result = await db.scalars(
        select(RoomAgent)
        .where(RoomAgent.room_id == room_id)
        .order_by(RoomAgent.position.asc(), RoomAgent.created_at.asc())
    )
    return [_agent_to_read(agent) for agent in result.all()]


@router.delete("/{room_id}/agents/{agent_key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_room_agent(
    room_id: str,
    agent_key: str,
    current_user: dict[str, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    user_id = current_user["user_id"]
    await _get_owned_active_room_or_404(db, room_id=room_id, user_id=user_id)

    agent = await db.scalar(
        select(RoomAgent).where(
            RoomAgent.room_id == room_id,
            RoomAgent.agent_key == agent_key,
        )
    )
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found.")

    await db.delete(agent)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
