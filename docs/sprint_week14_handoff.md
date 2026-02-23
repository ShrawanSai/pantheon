# Sprint Week 14 Handoff

## Sprint Goal
Introduce first-class user-owned `Agent` entities decoupled from rooms, refactor room agent assignment into a join model, and add standalone agent sessions with turn execution and conversation history read APIs.

## Completion Snapshot
- Tasks targeted: `W14-01` through `W14-05`.
- Local test suite at close: `151/151` passing.
- Ruff critical checks (`E9,F63,F7,F82`): passing.
- Migration head at close: `20260223_0016`.
- Staging summary:
  - Validation run attempted with `tmp_w14_staging_validate.py`.
  - `GET /api/v1/health`: `200`
  - `GET /api/v1/auth/me`: `200`
  - `POST /api/v1/agents`: `404` (`{"detail":"Not Found"}`), indicating staging deploy drift (Week 14 API changes not active on deployed instance).
  - Remaining Week 14 staging legs blocked until staging API redeploy.

## Delivered Artifacts
- W14-01 (Agent entity + CRUD):
  - Migration: `infra/alembic/versions/20260223_0014_create_agents_table.py`
  - ORM model: `apps/api/app/db/models.py` (`Agent`)
  - Schemas: `apps/api/app/schemas/agents.py`
  - Routes: `apps/api/app/api/v1/routes/agents.py`
  - Router registration: `apps/api/app/main.py`
  - Tests: `tests/test_agents_routes.py` (8 tests)

- W14-02 (RoomAgent join-table refactor):
  - Migration: `infra/alembic/versions/20260223_0015_refactor_room_agents_to_join_table.py`
  - ORM updates: `apps/api/app/db/models.py` (`RoomAgent.agent_id`, relationships)
  - Room route/schema updates for assignment by `agent_id`:
    - `apps/api/app/api/v1/routes/rooms.py`
    - `apps/api/app/schemas/rooms.py`
  - Cross-service reference updates:
    - `apps/api/app/api/v1/routes/sessions.py`
    - `apps/api/app/services/orchestration/orchestrator_manager.py`
    - `apps/api/app/services/tools/permissions.py`
  - Test updates:
    - `tests/test_rooms_routes.py`
    - `tests/test_orchestrator_manager.py`
    - `tests/test_tool_permissions.py`
    - `tests/test_sessions_routes.py`

- W14-03 (Session scope support):
  - Migration: `infra/alembic/versions/20260223_0016_session_standalone_agent_support.py`
  - ORM updates: `apps/api/app/db/models.py` (`Session.room_id` nullable, `Session.agent_id`, `ck_sessions_scope`)
  - Session schema updates: `apps/api/app/schemas/chat.py`
  - Scope constraint tests added in `tests/test_sessions_routes.py`

- W14-04 (Standalone sessions + turn branching + history reads):
  - Added standalone session routes:
    - `POST /api/v1/agents/{agent_id}/sessions`
    - `GET /api/v1/agents/{agent_id}/sessions`
  - Added history read routes:
    - `GET /api/v1/sessions/{session_id}/messages`
    - `GET /api/v1/sessions/{session_id}/turns`
  - Turn route now supports both room-scoped and standalone-scoped sessions:
    - Standalone turns run in `mode="standalone"`
    - Usage recording sets `room_id=None` and `agent_id=session.agent_id`
  - Files touched:
    - `apps/api/app/api/v1/routes/sessions.py`
    - `apps/api/app/schemas/chat.py`
  - Tests: `tests/test_standalone_sessions.py` (10 tests)

- W14-05 (Staging validation + handoff):
  - Staging validation script added: `tmp_w14_staging_validate.py`
  - Handoff document published (this file)

## Runtime Capability At Close
Compared with Week 13 close, the backend now additionally supports:
- first-class reusable `Agent` resources per user
- room membership via agent assignment join rows instead of inline room agent config
- dual session scope model (`room_id` XOR `agent_id`)
- standalone 1:1 agent sessions and standalone turn execution via existing turn route
- full chat history reads for frontend hydration using paginated session message/turn endpoints

## Migration Chain At Close
`20260221_0001 -> 20260221_0002 -> 20260221_0003 -> 20260221_0004 -> 20260221_0005 -> 20260222_0006 -> 20260222_0007 -> 20260222_0008 -> 20260222_0009 -> 20260222_0010 -> 20260222_0011 -> 20260222_0012 -> 20260223_0013 -> 20260223_0014 -> 20260223_0015 -> 20260223_0016`

## Carry-Forward Follow-Ups (Week 15+)
| ID | Severity | Description |
|---|---|---|
| F53 | Low | Search trigger remains heuristic (`search:` / `search for`) until planned ReAct/function-calling tool dispatch cycle. |
| F58 | Low | `uploaded_files.user_id` index remains deferred. |
| F62 | Low | `file_read` graph compile strategy remains accepted at current load. |
| F64 | Low | Worker DB URL precedence convention remains explicit deployment policy. |
| F70 | Medium | Staging deploy drift: Week 14 agent/session/history routes not active (`/api/v1/agents` returns 404); redeploy staging and re-run Week 14 validation legs. |

## Week 15 Entry Gates
1. Redeploy staging with Week 14 code and close F70 by re-running blocked W14 validation legs.
2. Lock Cycle 5 Part 2 scope (agent-private vs shared context layering in room sessions).
3. Decide whether to prioritize model-driven tool dispatch (`F53`) as a Week 15 anchor.
4. Keep F41 transaction policy locked for any new write paths.
