from __future__ import annotations

from decimal import Decimal
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    rooms: Mapped[list["Room"]] = relationship(back_populates="owner")
    started_sessions: Mapped[list["Session"]] = relationship(back_populates="started_by")


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    goal: Mapped[str | None] = mapped_column(Text(), nullable=True)
    current_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    pending_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    owner: Mapped["User"] = relationship(back_populates="rooms")
    agents: Mapped[list["RoomAgent"]] = relationship(back_populates="room")
    sessions: Mapped[list["Session"]] = relationship(back_populates="room")


class RoomAgent(Base):
    __tablename__ = "room_agents"
    __table_args__ = (UniqueConstraint("room_id", "agent_key", name="uq_room_agents_room_agent_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    room_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    model_alias: Mapped[str] = mapped_column(String(64), nullable=False)
    role_prompt: Mapped[str] = mapped_column(Text(), nullable=False)
    tool_permissions_json: Mapped[str] = mapped_column(
        Text(), nullable=False, server_default=text("'[]'")
    )
    position: Mapped[int] = mapped_column(Integer(), nullable=False, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    room: Mapped["Room"] = relationship(back_populates="agents")


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    room_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    started_by_user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    room: Mapped["Room"] = relationship(back_populates="sessions")
    started_by: Mapped["User"] = relationship(back_populates="started_sessions")
    turns: Mapped[list["Turn"]] = relationship(back_populates="session")
    messages: Mapped[list["Message"]] = relationship(back_populates="session")
    summaries: Mapped[list["SessionSummary"]] = relationship(back_populates="session")
    context_audits: Mapped[list["TurnContextAudit"]] = relationship(back_populates="session")


class Turn(Base):
    __tablename__ = "turns"
    __table_args__ = (UniqueConstraint("session_id", "turn_index", name="uq_turns_session_turn_index"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    turn_index: Mapped[int] = mapped_column(Integer(), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    user_input: Mapped[str] = mapped_column(Text(), nullable=False)
    assistant_output: Mapped[str | None] = mapped_column(Text(), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'completed'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    session: Mapped["Session"] = relationship(back_populates="turns")
    messages: Mapped[list["Message"]] = relationship(back_populates="turn")
    context_audits: Mapped[list["TurnContextAudit"]] = relationship(back_populates="turn")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    turn_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("turns.id", ondelete="SET NULL"), nullable=True, index=True
    )
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    agent_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    session: Mapped["Session"] = relationship(back_populates="messages")
    turn: Mapped["Turn | None"] = relationship(back_populates="messages")


class SessionSummary(Base):
    __tablename__ = "session_summaries"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    to_message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary_text: Mapped[str] = mapped_column(Text(), nullable=False)
    key_facts_json: Mapped[str] = mapped_column(Text(), nullable=False, server_default=text("'[]'"))
    open_questions_json: Mapped[str] = mapped_column(Text(), nullable=False, server_default=text("'[]'"))
    decisions_json: Mapped[str] = mapped_column(Text(), nullable=False, server_default=text("'[]'"))
    action_items_json: Mapped[str] = mapped_column(Text(), nullable=False, server_default=text("'[]'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    session: Mapped["Session"] = relationship(back_populates="summaries")


class TurnContextAudit(Base):
    __tablename__ = "turn_context_audit"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    turn_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("turns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model_alias: Mapped[str] = mapped_column(String(64), nullable=False)
    model_context_limit: Mapped[int] = mapped_column(Integer(), nullable=False)
    input_budget: Mapped[int] = mapped_column(Integer(), nullable=False)
    estimated_input_tokens_before: Mapped[int] = mapped_column(Integer(), nullable=False)
    estimated_input_tokens_after_summary: Mapped[int] = mapped_column(Integer(), nullable=False)
    estimated_input_tokens_after_prune: Mapped[int] = mapped_column(Integer(), nullable=False)
    summary_triggered: Mapped[bool] = mapped_column(Boolean(), nullable=False, server_default=text("false"))
    prune_triggered: Mapped[bool] = mapped_column(Boolean(), nullable=False, server_default=text("false"))
    overflow_rejected: Mapped[bool] = mapped_column(Boolean(), nullable=False, server_default=text("false"))
    output_reserve: Mapped[int] = mapped_column(Integer(), nullable=False)
    overhead_reserve: Mapped[int] = mapped_column(Integer(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    turn: Mapped["Turn"] = relationship(back_populates="context_audits")
    session: Mapped["Session"] = relationship(back_populates="context_audits")


class LlmCallEvent(Base):
    __tablename__ = "llm_call_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    room_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True
    )
    direct_session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    session_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True
    )
    turn_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("turns.id", ondelete="SET NULL"), nullable=True
    )
    step_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model_alias: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_model: Mapped[str] = mapped_column(String(128), nullable=False)
    input_tokens_fresh: Mapped[int] = mapped_column(Integer(), nullable=False)
    input_tokens_cached: Mapped[int] = mapped_column(Integer(), nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer(), nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer(), nullable=False)
    oe_tokens_computed: Mapped[float] = mapped_column(Numeric(20, 4), nullable=False)
    provider_cost_usd: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    credits_burned: Mapped[float] = mapped_column(Numeric(20, 4), nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    pricing_version: Mapped[str] = mapped_column(String(32), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class ToolCallEvent(Base):
    __tablename__ = "tool_call_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    room_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    turn_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("turns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_input_json: Mapped[str] = mapped_column(Text(), nullable=False)
    tool_output_json: Mapped[str] = mapped_column(Text(), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'success'"))
    latency_ms: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    credits_charged: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False, default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
