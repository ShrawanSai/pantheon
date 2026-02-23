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
    print("=== W15-07 staging validation ===")
    print("api_base:", api_base)

    def leg(name: str, fn):
        try:
            resp = fn()
        except Exception as exc:
            print(f"{name}: ERROR {exc}")
            return None
        if resp is None:
            return None
        body_preview = resp.text[:240].replace("\n", " ")
        print(f"{name}: {resp.status_code} {body_preview}")
        return resp

    health = leg("leg1 health", lambda: s.get(f"{api_base}/api/v1/health", timeout=30))

    token_resp = leg(
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

    leg("leg2 auth/me", lambda: s.get(f"{api_base}/api/v1/auth/me", headers=headers, timeout=30))

    # F70 closure legs
    create_agent = leg(
        "leg3 create agent",
        lambda: s.post(
            f"{api_base}/api/v1/agents",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "agent_key": f"w15_{uuid.uuid4().hex[:8]}",
                "name": "W15 Agent",
                "model_alias": "deepseek",
                "role_prompt": "W15 staging validation.",
                "tool_permissions": ["search"],
            },
            timeout=30,
        ),
    )
    agent_id = None
    if create_agent is not None and create_agent.status_code == 201:
        agent_id = create_agent.json()["id"]

    leg("leg4 list agents", lambda: s.get(f"{api_base}/api/v1/agents", headers=headers, timeout=30))

    standalone_session_id = None
    if agent_id is not None:
        create_session = leg(
            "leg5 create standalone session",
            lambda: s.post(f"{api_base}/api/v1/agents/{agent_id}/sessions", headers=headers, timeout=30),
        )
        if create_session is not None and create_session.status_code == 201:
            standalone_session_id = create_session.json()["id"]

    if standalone_session_id is not None:
        leg(
            "leg6 standalone turn",
            lambda: s.post(
                f"{api_base}/api/v1/sessions/{standalone_session_id}/turns",
                headers={**headers, "Content-Type": "application/json"},
                json={"message": "W15 standalone turn 1"},
                timeout=120,
            ),
        )
        leg(
            "leg7 standalone second turn",
            lambda: s.post(
                f"{api_base}/api/v1/sessions/{standalone_session_id}/turns",
                headers={**headers, "Content-Type": "application/json"},
                json={"message": "W15 standalone turn 2"},
                timeout=120,
            ),
        )
        leg(
            "leg8 standalone messages",
            lambda: s.get(f"{api_base}/api/v1/sessions/{standalone_session_id}/messages", headers=headers, timeout=30),
        )
        leg(
            "leg9 standalone turns",
            lambda: s.get(f"{api_base}/api/v1/sessions/{standalone_session_id}/turns", headers=headers, timeout=30),
        )

    # W15 legs 8-11 (numbered here independently in output labels)
    leg(
        "leg10 admin/settings regression",
        lambda: s.get(f"{api_base}/api/v1/admin/settings", headers=headers, timeout=30),
    )
    leg(
        "leg11 usage summary day",
        lambda: s.get(f"{api_base}/api/v1/admin/usage/summary?bucket=day", headers=headers, timeout=30),
    )

    # Heuristic search turn against standalone agent (if available) to at least exercise tool row path.
    if standalone_session_id is not None:
        leg(
            "leg12 standalone search turn",
            lambda: s.post(
                f"{api_base}/api/v1/sessions/{standalone_session_id}/turns",
                headers={**headers, "Content-Type": "application/json"},
                json={"message": "search latest AI pricing updates"},
                timeout=120,
            ),
        )

    _ = health
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
