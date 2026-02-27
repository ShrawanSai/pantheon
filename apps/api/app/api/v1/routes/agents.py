from __future__ import annotations

from datetime import datetime, timezone
import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.db.models import Agent, User
from apps.api.app.db.session import get_db
from apps.api.app.dependencies.auth import get_current_user
from apps.api.app.schemas.agents import AgentCreate, AgentListRead, AgentRead, AgentUpdate

router = APIRouter(prefix="/agents", tags=["agents"])


def _parse_tool_permissions(raw: str) -> list[str]:
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if isinstance(item, str)]


def _agent_to_read(agent: Agent) -> AgentRead:
    return AgentRead(
        id=agent.id,
        owner_user_id=agent.owner_user_id,
        agent_key=agent.agent_key,
        name=agent.name,
        model_alias=agent.model_alias,
        role_prompt=agent.role_prompt,
        tool_permissions=_parse_tool_permissions(agent.tool_permissions_json),
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


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


@router.post("", response_model=AgentRead, status_code=status.HTTP_201_CREATED)
async def create_agent(
    payload: AgentCreate,
    current_user: dict[str, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentRead:
    user_id = current_user["user_id"]
    email = (current_user.get("email") or "").strip() or f"{user_id}@placeholder.local"

    existing_user = await db.get(User, user_id)
    if existing_user is None:
        db.add(User(id=user_id, email=email))

    now = datetime.now(timezone.utc)
    agent = Agent(
        id=str(uuid4()),
        owner_user_id=user_id,
        agent_key=payload.agent_key,
        name=payload.name,
        model_alias=payload.model_alias,
        role_prompt=payload.role_prompt,
        tool_permissions_json=json.dumps(payload.tool_permissions),
        deleted_at=None,
        created_at=now,
        updated_at=now,
    )
    db.add(agent)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Agent key already exists for this user.") from exc

    await db.refresh(agent)
    return _agent_to_read(agent)


@router.get("", response_model=AgentListRead)
async def list_agents(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: dict[str, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentListRead:
    user_id = current_user["user_id"]
    conditions = (
        Agent.owner_user_id == user_id,
        Agent.deleted_at.is_(None),
    )
    total = int(await db.scalar(select(func.count(Agent.id)).where(*conditions)) or 0)
    rows = await db.scalars(
        select(Agent)
        .where(*conditions)
        .order_by(Agent.created_at.desc(), Agent.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return AgentListRead(agents=[_agent_to_read(agent) for agent in rows.all()], total=total)


@router.get("/{agent_id}", response_model=AgentRead)
async def get_agent(
    agent_id: str,
    current_user: dict[str, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentRead:
    user_id = current_user["user_id"]
    agent = await _get_owned_active_agent_or_404(db, agent_id=agent_id, user_id=user_id)
    return _agent_to_read(agent)


@router.patch("/{agent_id}", response_model=AgentRead)
async def update_agent(
    agent_id: str,
    payload: AgentUpdate,
    current_user: dict[str, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentRead:
    user_id = current_user["user_id"]
    agent = await _get_owned_active_agent_or_404(db, agent_id=agent_id, user_id=user_id)

    updates = payload.model_dump(exclude_unset=True)
    if "tool_permissions" in updates:
        agent.tool_permissions_json = json.dumps(updates.pop("tool_permissions"))
    if "agent_key" in updates:
        agent.agent_key = updates.pop("agent_key")
    if "name" in updates:
        agent.name = updates.pop("name")
    if "model_alias" in updates:
        agent.model_alias = updates.pop("model_alias")
    if "role_prompt" in updates:
        agent.role_prompt = updates.pop("role_prompt")
    agent.updated_at = datetime.now(timezone.utc)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Agent key already exists for this user.") from exc

    await db.refresh(agent)
    return _agent_to_read(agent)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: str,
    current_user: dict[str, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    user_id = current_user["user_id"]
    agent = await _get_owned_active_agent_or_404(db, agent_id=agent_id, user_id=user_id)
    now = datetime.now(timezone.utc)
    agent.deleted_at = now
    agent.updated_at = now
    suffix = f"_{int(now.timestamp())}"
    agent.agent_key = f"{agent.agent_key[:64 - len(suffix)]}{suffix}"
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
