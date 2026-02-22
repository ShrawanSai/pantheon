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

    session = requests.Session()
    print("=== W10-06 staging validation ===")

    health = session.get(f"{api_base}/api/v1/health", timeout=30)
    print("health:", health.status_code, health.text)
    if health.status_code != 200:
        return 1

    token_resp = session.post(
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

    auth_me = session.get(f"{api_base}/api/v1/auth/me", headers=headers, timeout=30)
    print("auth/me:", auth_me.status_code, auth_me.text)
    if auth_me.status_code != 200:
        return 1
    user_id = auth_me.json()["user_id"]

    room_resp = session.post(
        f"{api_base}/api/v1/rooms",
        headers={**headers, "Content-Type": "application/json"},
        json={
            "name": f"W10 Stage Room {uuid.uuid4().hex[:8]}",
            "goal": "W10 staging validation",
            "current_mode": "orchestrator",
        },
        timeout=30,
    )
    print("create room:", room_resp.status_code)
    if room_resp.status_code != 201:
        print(room_resp.text)
        return 1
    room_id = room_resp.json()["id"]

    agent_resp = session.post(
        f"{api_base}/api/v1/rooms/{room_id}/agents",
        headers={**headers, "Content-Type": "application/json"},
        json={
            "agent_key": "researcher",
            "name": "Researcher",
            "model_alias": "deepseek",
            "role_prompt": "Research quickly.",
            "tool_permissions": [],
        },
        timeout=30,
    )
    print("create agent:", agent_resp.status_code)
    if agent_resp.status_code != 201:
        print(agent_resp.text)
        return 1

    session_resp = session.post(f"{api_base}/api/v1/rooms/{room_id}/sessions", headers=headers, timeout=30)
    print("create session:", session_resp.status_code)
    if session_resp.status_code != 201:
        print(session_resp.text)
        return 1
    session_id = session_resp.json()["id"]

    turn_resp = session.post(
        f"{api_base}/api/v1/sessions/{session_id}/turns",
        headers={**headers, "Content-Type": "application/json"},
        json={"message": f"W10 turn validation {uuid.uuid4().hex[:8]}"},
        timeout=120,
    )
    print("create turn:", turn_resp.status_code, turn_resp.text)
    if turn_resp.status_code != 201:
        return 1
    turn_body = turn_resp.json()
    turn_id = turn_body["id"]
    print("turn balance_after:", turn_body.get("balance_after"), "low_balance:", turn_body.get("low_balance"))

    wallet_resp = session.get(f"{api_base}/api/v1/users/me/wallet", headers=headers, timeout=30)
    print("users wallet:", wallet_resp.status_code, wallet_resp.text)
    if wallet_resp.status_code != 200:
        return 1

    tx_resp = session.get(f"{api_base}/api/v1/users/me/transactions?limit=50&offset=0", headers=headers, timeout=30)
    print("users tx:", tx_resp.status_code, tx_resp.text)
    if tx_resp.status_code != 200:
        return 1

    tx_body = tx_resp.json()
    print("users tx total:", tx_body.get("total"))
    has_turn_ref = any(tx.get("reference_id") == turn_id for tx in tx_body.get("transactions", []))
    print("users tx contains turn debit:", has_turn_ref)

    admin_grant_resp = session.post(
        f"{api_base}/api/v1/admin/wallets/{user_id}/grant",
        headers={**headers, "Content-Type": "application/json"},
        json={"amount": 1.25, "note": "W10 staging grant"},
        timeout=30,
    )
    print("admin grant:", admin_grant_resp.status_code, admin_grant_resp.text)

    admin_wallet_resp = session.get(f"{api_base}/api/v1/admin/wallets/{user_id}", headers=headers, timeout=30)
    print("admin wallet:", admin_wallet_resp.status_code, admin_wallet_resp.text)

    admin_usage_resp = session.get(f"{api_base}/api/v1/admin/usage/summary", headers=headers, timeout=30)
    print("admin usage summary:", admin_usage_resp.status_code, admin_usage_resp.text)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
