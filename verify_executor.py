import httpx
import sys

BASE_URL = "http://127.0.0.1:8000/api/v1"
client = httpx.Client(base_url=BASE_URL, headers={"Authorization": "Bearer dev-override"}, timeout=60.0)

def _get_or_create_agent(name="Test Writer", role_prompt="You are a helpful assistant."):
    r = client.get("/agents")
    if r.status_code >= 400:
        print(f"Error {r.status_code} fetching agents: {r.text}")
        sys.exit(1)
    agents = r.json()
    if agents:
        return agents[0]["id"]
    
    # Create one if none
    r = client.post("/agents", json={
        "name": name,
        "agent_key": name.lower().replace(" ", "_"),
        "model_alias": "deepseek",
        "role_prompt": role_prompt,
        "tool_permissions": []
    })
    if r.status_code >= 400:
        print(f"Error {r.status_code} creating agent: {r.text}")
        sys.exit(1)
    return r.json()["id"]

def test_manual():
    print("Testing Manual Mode...")
    agent_id = _get_or_create_agent()
    r = client.post("/rooms", json={"name": "Manual Test", "current_mode": "manual"})
    if r.status_code != 201:
        print(f"Error creating room: {r.status_code} {r.text}")
        sys.exit(1)
    room_id = r.json()["id"]
    
    r = client.post(f"/rooms/{room_id}/agents", json={"agent_id": agent_id, "position": 1})
    r.raise_for_status()

    r = client.post(f"/rooms/{room_id}/sessions")
    r.raise_for_status()
    session_id = r.json()["id"]

    print("Submitting turn...")
    r = client.post(f"/sessions/{session_id}/turns", json={"message": "@test_writer Say hello."})
    if r.status_code != 201:
        print(f"Turn error: {r.status_code} {r.text}")
        sys.exit(1)
    print("Manual Turn Created:")
    print(r.json().get("assistant_output"))

if __name__ == "__main__":
    test_manual()
