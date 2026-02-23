from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from sqlalchemy import create_engine, text


def load_env(path: str) -> dict[str, str]:
    env: dict[str, str] = {}
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()
    return env


def _to_sync_driver(dsn: str) -> str:
    if dsn.startswith("postgresql+psycopg://"):
        return dsn
    if dsn.startswith("postgresql+asyncpg://"):
        return dsn.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    if dsn.startswith("postgresql://"):
        return dsn.replace("postgresql://", "postgresql+psycopg://", 1)
    return dsn


@dataclass
class LegResult:
    name: str
    status_code: int | None
    ok: bool
    detail: str


def _preview(resp: requests.Response) -> str:
    body = resp.text.replace("\n", " ")
    if len(body) > 240:
        body = body[:240] + "..."
    return body


def main() -> int:
    env = load_env(".env.staging")
    for key, value in env.items():
        os.environ.setdefault(key, value)

    api_base = env.get("RAILWAY_STAGING_API_URL") or "https://api-staging-3c02.up.railway.app"
    supabase_url = env["SUPABASE_URL"]
    supabase_anon_key = env["SUPABASE_ANON_KEY"]
    db_url = env.get("DATABASE_POOL_URL") or env.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_POOL_URL or DATABASE_URL is required for DB evidence.")
    db_url = _to_sync_driver(db_url)

    email = env.get("STAGING_TEST_EMAIL") or "msaishrawan@gmail.com"
    password = env.get("STAGING_TEST_PASSWORD") or "Shrawan@1999"

    results: list[LegResult] = []
    s = requests.Session()
    room_id: str | None = None
    room_session_id: str | None = None
    standalone_session_id: str | None = None
    created_agent_id: str | None = None
    search_turn_id: str | None = None
    plain_turn_id: str | None = None

    def run_leg(name: str, fn) -> requests.Response | None:
        try:
            resp = fn()
        except Exception as exc:  # pragma: no cover - operator script
            results.append(LegResult(name=name, status_code=None, ok=False, detail=f"ERROR {exc}"))
            print(f"{name}: ERROR {exc}")
            return None
        detail = _preview(resp)
        ok = 200 <= resp.status_code < 300
        results.append(LegResult(name=name, status_code=resp.status_code, ok=ok, detail=detail))
        print(f"{name}: {resp.status_code} {detail}")
        return resp

    print("=== W16 consolidated staging validation ===")
    print("api_base:", api_base)

    run_leg("leg12 health", lambda: s.get(f"{api_base}/api/v1/health", timeout=30))

    token_resp = run_leg(
        "token",
        lambda: s.post(
            f"{supabase_url}/auth/v1/token?grant_type=password",
            headers={"apikey": supabase_anon_key, "Content-Type": "application/json"},
            json={"email": email, "password": password},
            timeout=30,
        ),
    )
    if token_resp is None or token_resp.status_code != 200:
        return 1
    token = token_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    run_leg("leg13 auth/me", lambda: s.get(f"{api_base}/api/v1/auth/me", headers=headers, timeout=30))

    # F70 closure legs
    created_agent = run_leg(
        "leg1 create agent",
        lambda: s.post(
            f"{api_base}/api/v1/agents",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "agent_key": f"w16_{uuid.uuid4().hex[:8]}",
                "name": "W16 Agent",
                "model_alias": "deepseek",
                "role_prompt": "W16 staging flow.",
                "tool_permissions": ["search"],
            },
            timeout=30,
        ),
    )
    if created_agent is not None and created_agent.status_code == 201:
        created_agent_id = created_agent.json().get("id")

    run_leg("leg2 list agents", lambda: s.get(f"{api_base}/api/v1/agents", headers=headers, timeout=30))
    if created_agent_id:
        created_session = run_leg(
            "leg3 create standalone session",
            lambda: s.post(
                f"{api_base}/api/v1/agents/{created_agent_id}/sessions",
                headers=headers,
                timeout=30,
            ),
        )
        if created_session is not None and created_session.status_code == 201:
            standalone_session_id = created_session.json().get("id")

    if standalone_session_id:
        run_leg(
            "leg4 standalone turn",
            lambda: s.post(
                f"{api_base}/api/v1/sessions/{standalone_session_id}/turns",
                headers={**headers, "Content-Type": "application/json"},
                json={"message": "W16 standalone message 1"},
                timeout=120,
            ),
        )
        run_leg(
            "leg5 standalone second turn",
            lambda: s.post(
                f"{api_base}/api/v1/sessions/{standalone_session_id}/turns",
                headers={**headers, "Content-Type": "application/json"},
                json={"message": "W16 standalone message 2"},
                timeout=120,
            ),
        )
        run_leg(
            "leg6 standalone messages",
            lambda: s.get(
                f"{api_base}/api/v1/sessions/{standalone_session_id}/messages",
                headers=headers,
                timeout=30,
            ),
        )
        run_leg(
            "leg7 standalone turns",
            lambda: s.get(
                f"{api_base}/api/v1/sessions/{standalone_session_id}/turns",
                headers=headers,
                timeout=30,
            ),
        )

    # Build a room flow for W15/W16 DB evidence
    created_room = run_leg(
        "room create",
        lambda: s.post(
            f"{api_base}/api/v1/rooms",
            headers={**headers, "Content-Type": "application/json"},
            json={"name": "W16 Validation Room", "goal": "Validation", "current_mode": "manual"},
            timeout=30,
        ),
    )
    if created_room is not None and created_room.status_code == 201:
        room_id = created_room.json().get("id")
    if room_id and created_agent_id:
        run_leg(
            "room assign agent",
            lambda: s.post(
                f"{api_base}/api/v1/rooms/{room_id}/agents",
                headers={**headers, "Content-Type": "application/json"},
                json={"agent_id": created_agent_id},
                timeout=30,
            ),
        )
        room_session = run_leg(
            "room create session",
            lambda: s.post(f"{api_base}/api/v1/rooms/{room_id}/sessions", headers=headers, timeout=30),
        )
        if room_session is not None and room_session.status_code == 201:
            room_session_id = room_session.json().get("id")

    if room_session_id:
        search_turn = run_leg(
            "leg8 room search turn",
            lambda: s.post(
                f"{api_base}/api/v1/sessions/{room_session_id}/turns",
                headers={**headers, "Content-Type": "application/json"},
                json={"message": "search latest ai news @w16"},
                timeout=120,
            ),
        )
        if search_turn is not None and search_turn.status_code == 201:
            search_turn_id = search_turn.json().get("id")
        plain_turn = run_leg(
            "leg9 room plain turn",
            lambda: s.post(
                f"{api_base}/api/v1/sessions/{room_session_id}/turns",
                headers={**headers, "Content-Type": "application/json"},
                json={"message": "Explain the previous answer @w16"},
                timeout=120,
            ),
        )
        if plain_turn is not None and plain_turn.status_code == 201:
            plain_turn_id = plain_turn.json().get("id")

    # Regressions
    run_leg("leg14 admin/settings", lambda: s.get(f"{api_base}/api/v1/admin/settings", headers=headers, timeout=30))
    run_leg(
        "leg15 usage summary day",
        lambda: s.get(f"{api_base}/api/v1/admin/usage/summary?bucket=day", headers=headers, timeout=30),
    )

    # DB evidence
    print("=== DB evidence ===")
    with create_engine(db_url, pool_pre_ping=True).connect() as conn:
        head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        print("leg11 alembic head:", head)

        if search_turn_id:
            count_search = conn.execute(
                text("SELECT COUNT(*) FROM tool_call_events WHERE turn_id = :turn_id"),
                {"turn_id": search_turn_id},
            ).scalar()
            print("leg8 tool_call_events count for search turn:", int(count_search or 0))

        if plain_turn_id:
            count_plain = conn.execute(
                text("SELECT COUNT(*) FROM tool_call_events WHERE turn_id = :turn_id"),
                {"turn_id": plain_turn_id},
            ).scalar()
            print("leg9 tool_call_events count for plain turn:", int(count_plain or 0))

            role_rows = conn.execute(
                text(
                    """
                    SELECT role, source_agent_key
                    FROM messages
                    WHERE turn_id = :turn_id
                    ORDER BY created_at ASC, id ASC
                    """
                ),
                {"turn_id": plain_turn_id},
            ).all()
            print("leg10 message source_agent_key rows:", json.dumps([dict(row._mapping) for row in role_rows]))

    print("=== HTTP leg summary ===")
    for item in results:
        print(f"- {item.name}: status={item.status_code}, ok={item.ok}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

