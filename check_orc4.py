import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from sqlalchemy import select
from apps.api.app.db.session import get_session_factory
from apps.api.app.db.models import Room, RoomAgent, Agent

async def main():
    async_session_factory = get_session_factory()
    async with async_session_factory() as db:
        room = await db.scalar(select(Room).where(Room.name == "orc4"))
        if not room:
            print("Room 'orc4' not found")
            return
            
        print(f"Room: {room.name} (ID: {room.id})")
        
        room_agents = (
            await db.scalars(
                select(RoomAgent)
                .join(Agent, Agent.id == RoomAgent.agent_id)
                .where(RoomAgent.room_id == room.id)
                .order_by(RoomAgent.position.asc())
            )
        ).all()
        
        for ra in room_agents:
            agent = await db.scalar(select(Agent).where(Agent.id == ra.agent_id))
            print(f"- RoomAgent {ra.id} -> Agent: {agent.name} (Key: {agent.agent_key})")

if __name__ == "__main__":
    asyncio.run(main())
