#!/usr/bin/env python3
"""
Pantheon E2E Simulation
=======================
Runs a simulated multi-agent interaction using TestClient (in-process) with
a real OpenRouter LLM call (free tier model) and an in-memory SQLite database.

No running server required. Auth is overridden. Rate limiting is disabled.

Usage:
    python scripts/simulate_e2e.py

Requirements:
    OPENROUTER_API_KEY set in .env or environment.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import textwrap
import time

from dotenv import load_dotenv

load_dotenv()

if not os.getenv("OPENROUTER_API_KEY"):
    print("[ERROR] OPENROUTER_API_KEY not set. Add it to .env and retry.")
    sys.exit(1)

# Supabase env vars are required by config even though we won't use Supabase
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "dummy-service-role-key")
os.environ.setdefault("API_CORS_ALLOWED_ORIGINS", "http://localhost:3000")

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from apps.api.app.core.config import get_settings
from apps.api.app.db.models import Base, User
from apps.api.app.db.session import get_db
from apps.api.app.dependencies.auth import get_current_user
from apps.api.app.main import app

# ── In-memory database ───────────────────────────────────────────────────────

engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

USER_ID = "sim-user-001"
USER_EMAIL = "sim@pantheon.local"


async def _setup_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        session.add(User(id=USER_ID, email=USER_EMAIL))
        await session.commit()


asyncio.run(_setup_db())

# ── App overrides ────────────────────────────────────────────────────────────

get_settings.cache_clear()


async def _override_db():
    async with session_factory() as session:
        yield session


def _override_auth() -> dict[str, str]:
    return {"user_id": USER_ID, "email": USER_EMAIL}


app.dependency_overrides[get_db] = _override_db
app.dependency_overrides[get_current_user] = _override_auth
app.state.arq_redis = None  # disable rate limiting

client = TestClient(app, raise_server_exceptions=True)

# ── Display helpers ──────────────────────────────────────────────────────────

WIDTH = 72
DIVIDER = "-" * WIDTH
FREE_MODEL = "deepseek"  # deepseek/deepseek-v3.1-terminus


def section(title: str) -> None:
    print(f"\n{DIVIDER}")
    print(f"  {title}")
    print(DIVIDER)


def show_json(label: str, data: dict) -> None:
    print(f"\n  [{label}]")
    for line in json.dumps(data, indent=2).splitlines():
        print(f"    {line}")


def check(response, expected_status: int, label: str) -> dict:
    if response.status_code != expected_status:
        print(f"\n  [FAIL] {label}")
        print(f"    expected {expected_status}, got {response.status_code}")
        print(f"    body: {response.text[:600]}")
        sys.exit(1)
    print(f"\n  [OK] {label}  ->  HTTP {response.status_code}")
    return response.json()


def wrap(text: str, indent: str = "    ") -> str:
    return textwrap.fill(
        text.replace("\n", " "),
        width=WIDTH - len(indent),
        initial_indent=indent,
        subsequent_indent=indent,
    )


# ── 0. Health check ──────────────────────────────────────────────────────────

section("0  Health check")
check(client.get("/api/v1/health"), 200, "GET /api/v1/health")

# ── 1. Create two agents ─────────────────────────────────────────────────────

section("1  Create agents  (model: meta-llama/llama-3.3-70b-instruct:free)")

writer = check(
    client.post(
        "/api/v1/agents",
        json={
            "name": "Writer",
            "agent_key": "writer",
            "model_alias": FREE_MODEL,
            "role_prompt": (
                "You are a vivid creative writer. "
                "Respond with evocative, concise prose. "
                "Keep replies under 80 words."
            ),
            "tool_permissions": [],
        },
    ),
    201,
    "POST /api/v1/agents  (writer)",
)

analyst = check(
    client.post(
        "/api/v1/agents",
        json={
            "name": "Analyst",
            "agent_key": "analyst",
            "model_alias": FREE_MODEL,
            "role_prompt": (
                "You are a sharp critical analyst. "
                "Evaluate ideas with rigour and precision. "
                "Keep replies under 80 words."
            ),
            "tool_permissions": [],
        },
    ),
    201,
    "POST /api/v1/agents  (analyst)",
)

# ── 2. Standalone session — two turns ────────────────────────────────────────

section("2  Standalone session  (writer agent)")

standalone_session = check(
    client.post(f"/api/v1/agents/{writer['id']}/sessions"),
    201,
    "POST /api/v1/agents/{id}/sessions",
)
sid = standalone_session["id"]

print(f"\n  Sending turn 1 to standalone session {sid[:8]}... (waiting for rate limit)")
time.sleep(10)
t1 = check(
    client.post(
        f"/api/v1/sessions/{sid}/turns",
        json={"message": "Write a two-sentence description of a city that never sleeps."},
    ),
    201,
    "POST /sessions/{id}/turns  (turn 1)",
)
print(f"\n  Writer ->\n{wrap(t1['assistant_output'])}")

print(f"\n  Sending turn 2 (follow-up, waiting for rate limit)...")
time.sleep(10)
t2 = check(
    client.post(
        f"/api/v1/sessions/{sid}/turns",
        json={"message": "Now make it darker and more mysterious."},
    ),
    201,
    "POST /sessions/{id}/turns  (turn 2)",
)
print(f"\n  Writer ->\n{wrap(t2['assistant_output'])}")

# ── 3. Room — roundtable mode ────────────────────────────────────────────────

section("3  Room session — roundtable mode  (writer + analyst both respond)")

room = check(
    client.post(
        "/api/v1/rooms",
        json={
            "name": "Creative Council",
            "goal": "Develop ideas by combining writing flair and analytical rigor.",
            "current_mode": "roundtable",
        },
    ),
    201,
    "POST /api/v1/rooms",
)
room_id = room["id"]

check(
    client.post(
        f"/api/v1/rooms/{room_id}/agents",
        json={"agent_id": writer["id"], "position": 1},
    ),
    201,
    "POST /rooms/{id}/agents  (writer @ position 1)",
)
check(
    client.post(
        f"/api/v1/rooms/{room_id}/agents",
        json={"agent_id": analyst["id"], "position": 2},
    ),
    201,
    "POST /rooms/{id}/agents  (analyst @ position 2)",
)

room_session = check(
    client.post(f"/api/v1/rooms/{room_id}/sessions"),
    201,
    "POST /rooms/{id}/sessions",
)
rsid = room_session["id"]

print(f"\n  Sending roundtable turn to room session {rsid[:8]}... (waiting for rate limit)")
time.sleep(10)
rt = check(
    client.post(
        f"/api/v1/sessions/{rsid}/turns",
        json={
            "message": (
                "What makes a great opening line for a novel? "
                "Each of you respond from your own perspective."
            )
        },
    ),
    201,
    "POST /sessions/{id}/turns  (roundtable)",
)
print(f"\n  Roundtable output ->\n{wrap(rt['assistant_output'][:700])}")

# ── 4. Switch to orchestrator mode ───────────────────────────────────────────

section("4  Switch room to orchestrator mode")

check(
    client.patch(f"/api/v1/rooms/{room_id}/mode", json={"mode": "orchestrator"}),
    200,
    "PATCH /rooms/{id}/mode  ->  orchestrator",
)

print(f"\n  Sending orchestrator turn... (waiting for rate limit)")
time.sleep(15)
ot = check(
    client.post(
        f"/api/v1/sessions/{rsid}/turns",
        json={
            "message": (
                "Design the concept for a short story about an AI that gains empathy. "
                "Route to the most relevant specialist(s) and synthesize."
            )
        },
    ),
    201,
    "POST /sessions/{id}/turns  (orchestrator)",
)

output = ot["assistant_output"]
has_synthesis = "Manager synthesis" in output
print(f"\n  Manager synthesis present: {'YES' if has_synthesis else 'NO -- check routing'}")
print(f"\n  Orchestrator output ->\n{wrap(output[:900])}")

# ── 5. Message history ───────────────────────────────────────────────────────

section("5  Message history — room session")

history = check(
    client.get(f"/api/v1/sessions/{rsid}/messages"),
    200,
    "GET /sessions/{id}/messages",
)

messages = history["messages"]
print(f"\n  Total messages: {history['total']}")
print()
for msg in messages:
    role = msg["role"].upper()
    name = msg.get("agent_name") or "user"
    tag = f"[{role}:{name}]"
    preview = (msg.get("content") or "")[:90].replace("\n", " ")
    print(f"    {tag:<30}  {preview}")

# ── 6. List agents ───────────────────────────────────────────────────────────

section("6  List agents")

agents_list = check(
    client.get("/api/v1/agents"),
    200,
    "GET /api/v1/agents",
)
for a in agents_list["agents"]:
    print(f"    {a['agent_key']:<12}  id={a['id'][:8]}  model={a['model_alias']}")

# ── Done ─────────────────────────────────────────────────────────────────────

section("Simulation complete")
print(
    """  Endpoints exercised:
    GET  /api/v1/health
    POST /api/v1/agents                      (×2)
    GET  /api/v1/agents
    POST /api/v1/sessions                    (standalone)
    POST /api/v1/sessions/{id}/turns         (×2 standalone, ×1 roundtable, ×1 orchestrator)
    POST /api/v1/rooms
    POST /api/v1/rooms/{id}/agents           (×2)
    POST /api/v1/rooms/{id}/sessions
    PATCH /api/v1/rooms/{id}/mode
    GET  /api/v1/sessions/{id}/messages
"""
)
