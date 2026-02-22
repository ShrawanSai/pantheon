from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.db.models import Room


async def get_owned_active_room_or_404(db: AsyncSession, *, room_id: str, user_id: str) -> Room:
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
