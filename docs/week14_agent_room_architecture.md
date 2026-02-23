# Week 14 Architecture Design

Status: Drafted for supervisor approval before implementation.

## Scope
Week 14 introduces:
1. First-class standalone `Agent` entity (not room-bound).
2. `RoomAgent` as assignment join table (`room_id` + `agent_id`) rather than inline agent config holder.
3. Dual session scope model (`room` session vs standalone `agent` session).
4. Standalone turn execution through existing turn endpoint with type detection.

## Requirement 1: Standalone Agent

### Data Model
Add `agents` table:
- `id: VARCHAR(64)` PK
- `owner_user_id: VARCHAR(64)` FK -> `users.id` (`ON DELETE CASCADE`)
- `agent_key: VARCHAR(64)` (unique per owner)
- `name: VARCHAR(120)`
- `model_alias: VARCHAR(64)`
- `role_prompt: TEXT` (default empty string)
- `tool_permissions_json: TEXT` (default `'[]'`)
- `deleted_at: TIMESTAMPTZ` nullable
- `created_at`, `updated_at`
- `UNIQUE(owner_user_id, agent_key)`

Refactor `room_agents`:
- keep assignment metadata (`room_id`, `position`, `created_at`)
- add `agent_id` FK -> `agents.id`
- remove inline config columns after backfill
- `UNIQUE(room_id, agent_id)`

Refactor `sessions`:
- `room_id` becomes nullable
- add `agent_id` nullable FK -> `agents.id`
- add check constraint for exactly one scope:
  - `(room_id IS NOT NULL AND agent_id IS NULL) OR (room_id IS NULL AND agent_id IS NOT NULL)`

### API Shape
Agent CRUD:
- `POST /agents`
- `GET /agents`
- `GET /agents/{agent_id}`
- `PATCH /agents/{agent_id}`
- `DELETE /agents/{agent_id}` (soft delete)

Standalone session routes:
- `POST /agents/{agent_id}/sessions`
- `GET /agents/{agent_id}/sessions`

Room assignment routes:
- `POST /rooms/{room_id}/agents` with `agent_id`
- `DELETE /rooms/{room_id}/agents/{agent_id}` (unassign only)

## Requirement 2: Context Between Agents

### Current Week 14 Target
Week 14 implements session scope + standalone path, while preserving current room behavior.

### Week 15+ Dual-Layer Context Model (Design Locked)
Layer 1 (private scratchpad per agent):
- tool calls/results and agent-local execution traces.

Layer 2 (shared room context):
- user messages
- final outputs from each agent

Planned message metadata extension:
- `visibility: shared|private`
- normalized agent key field for private scoping

Standalone sessions:
- no shared layer; context is naturally single-agent.

## Requirement 3: Tool Invocation Model

### Week 14 Runtime
- preserve current tool path while session/entity refactor is delivered safely.

### Week 16 Direction (Design Locked)
- replace heuristic triggers with ReAct-style function-calling tool loop.
- LLM decides tool usage; wrappers keep telemetry and permission control.

## Turn Endpoint Branching (Week 14)
`POST /sessions/{session_id}/turns`:
- if `session.room_id` set:
  - existing room flow (`manual/tag/roundtable/orchestrator`)
- if `session.agent_id` set:
  - standalone direct single-agent flow
  - no room-mode dispatch logic
  - context from this standalone session history
  - response mode: `"standalone"`

## Migration Plan
1. `20260223_0014_create_agents_table.py`
2. `20260223_0015_refactor_room_agents_to_join_table.py`
3. `20260223_0016_session_standalone_agent_support.py`
4. optional `0017` only if nullability adjustments for usage/tool rows are required by discovered constraints.

## Risks and Safeguards
- Risk: breaking existing room turns during refactor.
  - Safeguard: regression tests on room assignment and room turn flow.
- Risk: migration data backfill mismatch from legacy `room_agents` rows.
  - Safeguard: deterministic mapping and migration validation queries.
- Risk: mixed scope session records.
  - Safeguard: DB-level check constraint + ORM tests.

## Block Execution Plan

### Block 1
- W14-01: agents entity + CRUD
- W14-02: room agent join refactor + migration
- W14-03: session scope refactor

Checkpoint required before Block 2.

### Block 2
- W14-04: standalone routes + turn branching
- W14-05: staging validation + Week 14 handoff
