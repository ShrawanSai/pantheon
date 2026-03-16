"""
Comprehensive API route tests for Pantheon.
Run with: python test_routes.py
"""
import json
import sys
import uuid
import urllib.request
import urllib.error

_RUN_ID = str(uuid.uuid4())[:8]

BASE = "http://127.0.0.1:8099"
USER_TOKEN = "dev-override"
ADMIN_TOKEN = "admin-override"

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
WARN = "\033[93mSKIP\033[0m"

results = []

def req(method, path, token=None, body=None, expected=(200, 201, 204), label=None):
    url = BASE + path
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body else None
    try:
        r = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(r, timeout=10) as resp:
            status = resp.status
            try:
                payload = json.loads(resp.read())
            except Exception:
                payload = {}
    except urllib.error.HTTPError as e:
        status = e.code
        try:
            payload = json.loads(e.read())
        except Exception:
            payload = {}
    except Exception as e:
        status = 0
        payload = {"error": str(e)}

    ok = status in (expected if isinstance(expected, tuple) else (expected,))
    icon = PASS if ok else FAIL
    name = label or f"{method} {path}"
    print(f"  {icon} [{status}] {name}")
    results.append((ok, name, status, payload))
    return status, payload


def section(title):
    print(f"\n{'='*55}")
    print(f"  {title}")
    print(f"{'='*55}")


# ── Health ────────────────────────────────────────────────
section("Health & Public")
req("GET", "/api/v1/health", expected=(200, 404))
req("GET", "/api/v1/graph-check", expected=(200, 404))

# ── Auth ──────────────────────────────────────────────────
section("Auth")
req("GET", "/api/v1/auth/me", token=USER_TOKEN)
req("GET", "/api/v1/auth/me", expected=(401,), label="GET /auth/me (no token)")

# ── Agents CRUD ───────────────────────────────────────────
section("Agents")
_, agents_list = req("GET", "/api/v1/agents", token=USER_TOKEN)

create_status, agent = req("POST", "/api/v1/agents", token=USER_TOKEN, body={
    "agent_key": f"test-route-{_RUN_ID}",
    "name": "Test Agent",
    "model_alias": "gemini-flash",
    "role_prompt": "You are a helpful assistant.",
    "tool_permissions": [],
})
agent_id = agent.get("id") if create_status in (200, 201) else None

if agent_id:
    req("GET", f"/api/v1/agents/{agent_id}", token=USER_TOKEN)
    req("PATCH", f"/api/v1/agents/{agent_id}", token=USER_TOKEN, body={"name": "Updated Agent"})
    req("DELETE", f"/api/v1/agents/{agent_id}", token=USER_TOKEN, expected=(200, 204))
    req("GET", f"/api/v1/agents/{agent_id}", token=USER_TOKEN, expected=(404,), label="GET deleted agent → 404")
else:
    print(f"  {WARN} Skipping agent sub-tests (creation failed)")

# ── Rooms CRUD ────────────────────────────────────────────
section("Rooms")
req("GET", "/api/v1/rooms", token=USER_TOKEN)

create_status, room = req("POST", "/api/v1/rooms", token=USER_TOKEN, body={
    "name": "Test Room",
    "current_mode": "manual",
})
room_id = room.get("id") if create_status in (200, 201) else None

if room_id:
    req("GET", f"/api/v1/rooms/{room_id}", token=USER_TOKEN)

    # Create an agent for room agent tests
    _, room_agent = req("POST", "/api/v1/agents", token=USER_TOKEN, body={
        "agent_key": f"test-room-{_RUN_ID}",
        "name": "Room Agent",
        "model_alias": "gemini-flash",
        "role_prompt": "You help with room tests.",
        "tool_permissions": [],
    })
    room_agent_id = room_agent.get("id")

    if room_agent_id:
        req("POST", f"/api/v1/rooms/{room_id}/agents", token=USER_TOKEN, body={"agent_id": room_agent_id})
        req("GET", f"/api/v1/rooms/{room_id}/agents", token=USER_TOKEN)
        req("DELETE", f"/api/v1/rooms/{room_id}/agents/{room_agent_id}", token=USER_TOKEN, expected=(200, 204))
        req("DELETE", f"/api/v1/agents/{room_agent_id}", token=USER_TOKEN, expected=(200, 204))

    req("PATCH", f"/api/v1/rooms/{room_id}/mode", token=USER_TOKEN, body={"mode": "roundtable"})
else:
    print(f"  {WARN} Skipping room sub-tests (creation failed)")

# ── Sessions ─────────────────────────────────────────────
section("Sessions")

session_id = None
if room_id:
    create_status, session = req("POST", f"/api/v1/rooms/{room_id}/sessions", token=USER_TOKEN, body={})
    session_id = session.get("id") if create_status in (200, 201) else None
    req("GET", f"/api/v1/rooms/{room_id}/sessions", token=USER_TOKEN)

if session_id:
    req("PATCH", f"/api/v1/sessions/{session_id}", token=USER_TOKEN, body={"name": "Renamed Session"})
    req("GET", f"/api/v1/sessions/{session_id}/messages", token=USER_TOKEN)
    req("GET", f"/api/v1/sessions/{session_id}/turns", token=USER_TOKEN)
    req("GET", f"/api/v1/sessions/{session_id}/analytics", token=USER_TOKEN)
    req("GET", f"/api/v1/sessions/{session_id}/files", token=USER_TOKEN)
else:
    print(f"  {WARN} Skipping session sub-tests (creation failed)")

# ── User Wallet ───────────────────────────────────────────
section("User Wallet & Billing")
req("GET", "/api/v1/users/me/wallet", token=USER_TOKEN)
req("GET", "/api/v1/users/me/usage", token=USER_TOKEN)
req("GET", "/api/v1/users/me/transactions", token=USER_TOKEN)
req("POST", "/api/v1/users/me/wallet/top-up", token=USER_TOKEN, body={"amount": 10, "currency": "usd"}, expected=(200, 201, 400, 422))

# ── Admin ─────────────────────────────────────────────────
section("Admin (admin-override token)")
req("GET", "/api/v1/admin/settings", token=ADMIN_TOKEN)
req("GET", "/api/v1/admin/pricing", token=ADMIN_TOKEN)
req("GET", "/api/v1/admin/usage/summary", token=ADMIN_TOKEN)
req("GET", "/api/v1/admin/analytics/active-users", token=ADMIN_TOKEN)
import datetime
today = datetime.date.today().isoformat()
week_ago = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
req("GET", f"/api/v1/admin/analytics/usage?start_date={week_ago}&end_date={today}", token=ADMIN_TOKEN)

# Admin access control
req("GET", "/api/v1/admin/settings", token=USER_TOKEN, expected=(403,), label="GET /admin/settings (non-admin → 403)")

# ── Cleanup ───────────────────────────────────────────────
section("Cleanup")
if session_id and room_id:
    req("DELETE", f"/api/v1/rooms/{room_id}/sessions/{session_id}", token=USER_TOKEN, expected=(200, 204))
if room_id:
    req("DELETE", f"/api/v1/rooms/{room_id}", token=USER_TOKEN, expected=(200, 204))

# ── Summary ───────────────────────────────────────────────
section("Results")
passed = sum(1 for r in results if r[0])
failed = [r for r in results if not r[0]]
total = len(results)
print(f"\n  {PASS} Passed: {passed}/{total}")
if failed:
    print(f"  {FAIL} Failed ({len(failed)}):")
    for _, name, status, payload in failed:
        detail = payload.get("detail", "") if isinstance(payload, dict) else ""
        print(f"       [{status}] {name}  {detail}")

sys.exit(0 if not failed else 1)
