# Pantheon MVP - Sprint Week 14 Checklist

Sprint window: Week 14 (Cycle 5 Part 1 - Agent Entity + Standalone Sessions)  
Owner: Codex  
Reviewer: External supervising engineer  
Last updated: 2026-02-23

## Sprint Goal
Introduce `Agent` as a first-class entity decoupled from rooms, refactor room assignment to a join model, add standalone agent sessions, and validate standalone turn flow end-to-end.

## Baseline
- Local tests at sprint open: `130` passing.
- Migration head at sprint open: `20260223_0013`.

## Entry Gate Decisions (Locked)
1. Enforcement default-on: deferred (document trigger criteria only; no env/default flip).
2. CSV/export implementation: out of scope (JSON summary remains source).
3. `initiated_by` for debits: documentation-only convention (no schema change).

## Definition of Done (Week 14)
- `agents` table + ORM + CRUD routes implemented and tested.
- `room_agents` converted to agent-assignment join model with data migration from legacy inline agent fields.
- `sessions` support exactly one scope: room session OR standalone agent session.
- Standalone session routes exist and standalone turn submission works through existing `/sessions/{session_id}/turns` endpoint.
- Staging validation confirms standalone + room flows, migrations, and admin settings regression.
- Week 14 handoff is published with chain and carry-forwards.

## Working Rules
- Execute as two blocks with supervisor checkpoint at each block end.
- Block 1: `W14-01`, `W14-02`, `W14-03`.
- Block 2: `W14-04`, `W14-05`.
- If a blocker is hit, stop and raise immediately; do not silently workaround.

## Technical Constraints
- Keep F41 transaction policy for all write paths.
- Migration ordering must be explicit and reversible.
- If migration complexity requires split (`0015a/0015b`), document why and maintain data integrity.
- Existing room-scoped behavior must remain backward-compatible.

## Dependency Rules
- `W14-01 -> W14-02 -> W14-03 -> W14-04 -> W14-05`
- `W14-04` depends on both schema refactors from `W14-02` and `W14-03`.

## Week 14 Task Checklist
| ID | Task | Status | Acceptance Criteria | Evidence / Notes |
|---|---|---|---|---|
| W14-01 | `agents` table + ORM + CRUD routes | IN_REVIEW | Migration `20260223_0014_create_agents_table.py`; `Agent` ORM; routes `POST/GET/PATCH/DELETE /agents`; tests for create/list/get/update/delete + ownership/duplicate behavior | Implemented: migration `0014`, `apps/api/app/schemas/agents.py`, `apps/api/app/api/v1/routes/agents.py`, `apps/api/app/main.py` router include, `tests/test_agents_routes.py` (8 tests passing). |
| W14-02 | Refactor `RoomAgent` into join table + data migration | IN_REVIEW | Migration `20260223_0015_refactor_room_agents_to_join_table.py` backfills `agents` and `room_agents.agent_id`; drops inline agent config columns; updates room routes/schemas and references in sessions/orchestration; assignment tests added | Implemented: model + migration refactor, rooms assignment API now `agent_id` based, sessions/orchestrator/permissions read from joined `Agent`, room assignment tests updated (duplicate + ownership + list/delete regression all passing). |
| W14-03 | Session scope refactor (`room_id` nullable + `agent_id`) | IN_REVIEW | Migration `20260223_0016_session_standalone_agent_support.py`; check constraint for exactly one scope; ORM updates; tests for valid room sessions and invalid scope combinations | Implemented: `Session.room_id` nullable, `Session.agent_id` + `ck_sessions_scope`, `SessionRead` includes `agent_id`; added DB constraint tests for invalid both-set / neither-set scopes. |
| W14-04 | Standalone agent sessions + turn flow branch | IN_REVIEW | Routes `POST/GET /agents/{agent_id}/sessions`; existing turn endpoint detects room vs standalone session and executes standalone single-agent path; response mode includes `standalone`; usage records support `room_id=None`; tests for standalone creation/list/turn/context carryover | Implemented with added history read APIs: `GET /sessions/{session_id}/messages`, `GET /sessions/{session_id}/turns`; added `tests/test_standalone_sessions.py` (10 tests), updated session/chat schemas and turn usage attribution (`agent_id` set for standalone usage rows). |
| W14-05 | Staging validation + handoff | IN_REVIEW | Staging legs pass for standalone and room paths; admin settings regression pass; `docs/sprint_week14_handoff.md` published | Staging run attempted via `tmp_w14_staging_validate.py`; blocked by staging deploy drift (`POST /api/v1/agents` returns 404). Handoff drafted with per-leg status and carry-forward (`F70`). |

## Current Focus
- Block 2 implementation complete locally; awaiting supervisor review and staging redeploy to close staging validation legs.

## Carry-Forward At Week 14 Entry
| ID | Severity | Description |
|---|---|---|
| F53 | Low | Heuristic search trigger remains (superseded by Week 16 ReAct direction). |
| F58 | Low | `uploaded_files.user_id` index deferred. |
| F62 | Low | Per-turn file_read graph compile behavior accepted for current throughput. |
| F64 | Low | Worker DB URL precedence policy remains explicit deployment convention. |

## Change Log
- 2026-02-23: Initialized Week 14 checklist from supervisor prescription with block structure, dependencies, acceptance criteria, and entry carry-forwards.
- 2026-02-23: Marked sprint as not started pending supervisor approval of Week 14 architecture and checklist.
- 2026-02-23: Completed Block 1 implementation (`W14-01` to `W14-03`) and marked all three tasks `IN_REVIEW` pending supervisor checkpoint.
- 2026-02-23: Completed Block 2 local implementation (`W14-04`), added standalone/history tests, and attempted `W14-05` staging validation (blocked by deploy drift on `/api/v1/agents`).
