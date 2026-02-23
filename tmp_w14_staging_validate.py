from __future__ import annotations

import uuid
from pathlib import Path

import requests


def load_env(path: str) -> dict[str, str]:
    env: dict[str, str] = {}
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()
    return env


def main() -> int:
    env = load_env(".env.staging")
    api_base = env.get("RAILWAY_STAGING_API_URL") or "https://api-staging-3c02.up.railway.app"
    supabase_url = env["SUPABASE_URL"]
    supabase_anon_key = env["SUPABASE_ANON_KEY"]

    email = "msaishrawan@gmail.com"
    password = "Shrawan@1999"

    s = requests.Session()
    print("=== W14-05 staging validation ===")
    print("api_base:", api_base)

    health = s.get(f"{api_base}/api/v1/health", timeout=30)
    print("leg1 health:", health.status_code)
    if health.status_code != 200:
        print(health.text)
        return 1

    token_resp = s.post(
        f"{supabase_url}/auth/v1/token?grant_type=password",
        headers={"apikey": supabase_anon_key, "Content-Type": "application/json"},
        json={"email": email, "password": password},
        timeout=30,
    )
    print("token:", token_resp.status_code)
    if token_resp.status_code != 200:
        print(token_resp.text)
        return 1
    token = token_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    auth_me = s.get(f"{api_base}/api/v1/auth/me", headers=headers, timeout=30)
    print("auth/me:", auth_me.status_code)
    if auth_me.status_code != 200:
        print(auth_me.text)
        return 1
    user_id = auth_me.json()["user_id"]

    # W14 standalone legs
    create_agent = s.post(
        f"{api_base}/api/v1/agents",
        headers={**headers, "Content-Type": "application/json"},
        json={
            "agent_key": f"w14_{uuid.uuid4().hex[:8]}",
            "name": "Standalone Agent",
            "model_alias": "deepseek",
            "role_prompt": "Be concise.",
            "tool_permissions": [],
        },
        timeout=30,
    )
    print("leg2 create agent:", create_agent.status_code)
    if create_agent.status_code != 201:
        print(create_agent.text)
        return 1
    agent_id = create_agent.json()["id"]

    list_agents = s.get(f"{api_base}/api/v1/agents", headers=headers, timeout=30)
    print("leg3 list agents:", list_agents.status_code)
    if list_agents.status_code != 200:
        print(list_agents.text)
        return 1

    create_standalone_session = s.post(
        f"{api_base}/api/v1/agents/{agent_id}/sessions", headers=headers, timeout=30
    )
    print("leg4 create standalone session:", create_standalone_session.status_code)
    if create_standalone_session.status_code != 201:
        print(create_standalone_session.text)
        return 1
    standalone_session_id = create_standalone_session.json()["id"]

    first_turn = s.post(
        f"{api_base}/api/v1/sessions/{standalone_session_id}/turns",
        headers={**headers, "Content-Type": "application/json"},
        json={"message": f"W14 standalone first {uuid.uuid4().hex[:6]}"},
        timeout=120,
    )
    print("leg5 standalone turn:", first_turn.status_code)
    if first_turn.status_code != 201:
        print(first_turn.text)
        return 1
    print("leg5 mode:", first_turn.json().get("mode"))

    second_turn = s.post(
        f"{api_base}/api/v1/sessions/{standalone_session_id}/turns",
        headers={**headers, "Content-Type": "application/json"},
        json={"message": "W14 standalone second turn"},
        timeout=120,
    )
    print("leg6 standalone second turn:", second_turn.status_code)
    if second_turn.status_code != 201:
        print(second_turn.text)
        return 1

    messages_resp = s.get(
        f"{api_base}/api/v1/sessions/{standalone_session_id}/messages",
        headers=headers,
        timeout=30,
    )
    print("leg7 session messages:", messages_resp.status_code)
    if messages_resp.status_code != 200:
        print(messages_resp.text)
        return 1
    print("leg7 messages total:", messages_resp.json().get("total"))

    turns_resp = s.get(
        f"{api_base}/api/v1/sessions/{standalone_session_id}/turns",
        headers=headers,
        timeout=30,
    )
    print("leg8 session turns:", turns_resp.status_code)
    if turns_resp.status_code != 200:
        print(turns_resp.text)
        return 1
    print("leg8 turns total:", turns_resp.json().get("total"))

    # Room regression leg
    create_room = s.post(
        f"{api_base}/api/v1/rooms",
        headers={**headers, "Content-Type": "application/json"},
        json={
            "name": f"W14 Room {uuid.uuid4().hex[:8]}",
            "goal": "Room regression check",
            "current_mode": "orchestrator",
        },
        timeout=30,
    )
    print("create room:", create_room.status_code)
    if create_room.status_code != 201:
        print(create_room.text)
        return 1
    room_id = create_room.json()["id"]

    assign = s.post(
        f"{api_base}/api/v1/rooms/{room_id}/agents",
        headers={**headers, "Content-Type": "application/json"},
        json={"agent_id": agent_id},
        timeout=30,
    )
    print("room assign:", assign.status_code)
    if assign.status_code != 201:
        print(assign.text)
        return 1

    room_session = s.post(f"{api_base}/api/v1/rooms/{room_id}/sessions", headers=headers, timeout=30)
    print("room session:", room_session.status_code)
    if room_session.status_code != 201:
        print(room_session.text)
        return 1
    room_session_id = room_session.json()["id"]

    room_turn = s.post(
        f"{api_base}/api/v1/sessions/{room_session_id}/turns",
        headers={**headers, "Content-Type": "application/json"},
        json={"message": "W14 room mode regression check"},
        timeout=120,
    )
    print("leg9 room turn:", room_turn.status_code)
    if room_turn.status_code != 201:
        print(room_turn.text)
        return 1
    print("leg9 room mode:", room_turn.json().get("mode"))

    admin_settings = s.get(f"{api_base}/api/v1/admin/settings", headers=headers, timeout=30)
    print("leg10 admin/settings:", admin_settings.status_code)
    if admin_settings.status_code != 200:
        print(admin_settings.text)
        return 1

    print("W14 staging legs completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
