from __future__ import annotations

import asyncio
import unittest
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from apps.api.app.db.models import Base, Message, Session, User, Agent


class MessageSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.session_factory = async_sessionmaker(
            bind=cls.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

        async def init_db() -> None:
            async with cls.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

        asyncio.run(init_db())

    @classmethod
    def tearDownClass(cls) -> None:
        async def shutdown_db() -> None:
            async with cls.engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            await cls.engine.dispose()

        asyncio.run(shutdown_db())

    async def _seed_session(self) -> str:
        user_id = str(uuid4())
        agent_id = str(uuid4())
        session_id = str(uuid4())
        async with self.session_factory() as session:
            session.add(User(id=user_id, email=f"{user_id}@example.com"))
            session.add(
                Agent(
                    id=agent_id,
                    owner_user_id=user_id,
                    agent_key="agent",
                    name="Agent",
                    model_alias="deepseek",
                    role_prompt="Role",
                    tool_permissions_json="[]",
                )
            )
            session.add(
                Session(
                    id=session_id,
                    room_id=None,
                    agent_id=agent_id,
                    started_by_user_id=user_id,
                )
            )
            await session.commit()
        return session_id

    def test_message_visibility_defaults_to_shared(self) -> None:
        async def run() -> str:
            session_id = await self._seed_session()
            message_id = str(uuid4())
            async with self.session_factory() as session:
                session.add(
                    Message(
                        id=message_id,
                        turn_id=None,
                        session_id=session_id,
                        role="user",
                        mode="standalone",
                        content="hello",
                    )
                )
                await session.commit()
                stored = await session.get(Message, message_id)
                assert stored is not None
                return stored.visibility

        visibility = asyncio.run(run())
        self.assertEqual(visibility, "shared")

    def test_message_agent_key_nullable(self) -> None:
        async def run() -> Message:
            session_id = await self._seed_session()
            message_id = str(uuid4())
            async with self.session_factory() as session:
                session.add(
                    Message(
                        id=message_id,
                        turn_id=None,
                        session_id=session_id,
                        role="assistant",
                        visibility="shared",
                        agent_key=None,
                        mode="standalone",
                        content="response",
                    )
                )
                await session.commit()
                stored = await session.get(Message, message_id)
                assert stored is not None
                return stored

        message = asyncio.run(run())
        self.assertIsNone(message.agent_key)


if __name__ == "__main__":
    unittest.main()
