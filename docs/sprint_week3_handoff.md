# Pantheon MVP - Sprint Week 3 Handoff

Date: 2026-02-21
Owner: Codex
Reviewer: External supervising engineer

## Sprint Goal
Establish the first end-to-end session-to-turn execution loop on production modules: session CRUD, LLM gateway baseline, context budget enforcement, and full audit trail persistence.

## Completion Snapshot
- W3-01 through W3-07: complete.
- Validation status:
  - `unittest`: `31/31` passing
  - `ruff` critical rules (`E9,F63,F7,F82`): passing
- Staging smoke evidence at close:
  - `GET /api/v1/health` → `200`
  - `GET /api/v1/auth/me` (no bearer) → `401`
  - Railway staging worker: healthy, Redis connected
  - Staging DB: migrated to `20260221_0004 (head)` via Alembic

## Delivered Artifacts

### Gates (pre-feature)
- Supabase service role key rotated and applied across all environments (F24 / W3-02)
- `docs/week3_context_budget_design.md` — locked context budget policy with all clarifications applied (F23 / W3-03)
- `docs/week3_dev_environment_strategy.md` — staging-by-default strategy documented and staging stack provisioned (F25 / W3-04)

### Migrations
- `infra/alembic/versions/20260221_0004_session_summaries_context_audit.py`
  - `session_summaries` table with structured JSON fields and session FK
  - `turn_context_audit` table with per-turn context budget audit trail

### ORM Models (extensions to `apps/api/app/db/models.py`)
- `Turn` — turn index, mode, user input, assistant output, status
- `Message` — role, agent name, mode, content; nullable `turn_id` (SET NULL on delete)
- `SessionSummary` — summary text + structured JSON fields (key_facts, decisions, open_questions, action_items)
- `TurnContextAudit` — full budget audit fields per turn

### Services
- `apps/api/app/services/llm/gateway.py` — `LlmGateway` Protocol + `OpenRouterLlmGateway` via `langchain_core`; `GatewayRequest/Response/Usage` dataclasses; token estimation fallback; `get_llm_gateway()` for DI
- `apps/api/app/services/usage/meter.py` — `compute_oe_tokens` and `compute_credits_burned` implementing approved OE formula
- `apps/api/app/services/usage/recorder.py` — `UsageRecorder` stub (drop record; persistence deferred as F38); `get_usage_recorder()` for DI
- `apps/api/app/services/orchestration/context_manager.py` — `ContextManager` with 3-phase guardrail (summarize → prune → reject), token estimation, `ContextPreparation` dataclass, `ContextBudgetExceeded` exception

### Routes
- `apps/api/app/api/v1/routes/sessions.py`
  - `POST /api/v1/rooms/{room_id}/sessions` — create session with ownership guard
  - `GET /api/v1/rooms/{room_id}/sessions` — list non-deleted sessions for owned room
  - `DELETE /api/v1/rooms/{room_id}/sessions/{session_id}` — soft delete
  - `POST /api/v1/sessions/{session_id}/turns` — full turn pipeline: context guardrail → LLM gateway → turn+message write → summary+audit persistence → usage hook; overflow → `422 context_budget_exceeded`

### Config (extensions to `apps/api/app/core/config.py`)
- `CONTEXT_MAX_OUTPUT_TOKENS` (default 2048)
- `CONTEXT_SUMMARY_TRIGGER_RATIO` (default 0.70)
- `CONTEXT_PRUNE_TRIGGER_RATIO` (default 0.90)
- `CONTEXT_MANDATORY_SUMMARY_TURN` (default 8)
- `CONTEXT_DEFAULT_MODEL_LIMIT` (default 8192)
- `CONTEXT_RECENT_TURNS_TO_KEEP` (default 4)

### Test Coverage
- `tests/test_sessions_routes.py` — 8 tests:
  - Session create (owned room, not-owned room)
  - Session list (owned only)
  - Session delete (soft delete, not-owned 404)
  - Turn create (writes turn + 2 messages + audit; 1 gateway call; 1 usage record)
  - Turn create (second turn: `turn_index=2`, 4 total messages)
  - Turn create (50k char overflow → `422`)

## Runtime/Product Capability At Close

### Session lifecycle
- `POST /api/v1/rooms/{room_id}/sessions`
- `GET /api/v1/rooms/{room_id}/sessions`
- `DELETE /api/v1/rooms/{room_id}/sessions/{session_id}` (soft delete)

### Turn execution
- `POST /api/v1/sessions/{session_id}/turns`
  - Context budget enforced (summarize → prune → reject cascade)
  - First agent in room selected as executor (orchestrator mode)
  - History loaded from `messages` table
  - Latest summary injected as system context
  - `TurnContextAudit` written per turn
  - `SessionSummary` written when summary triggered
  - Usage hook called (stub — no DB persistence yet)
  - Overflow rejected with structured 422 error

## Open Follow-Ups (Carry Into Week 4)

| ID | Severity | Description |
|----|----------|-------------|
| F35 | Medium | `_get_owned_active_room_or_404` is duplicated in `rooms.py` and `sessions.py`; extract to shared module before adding more route groups. |
| F36 | Medium | `turn_index` derived via `MAX + 1` without transaction lock; concurrent creation races to unique-constraint conflict. Add `IntegrityError` handler or sequence. |
| F37 | High | Summarization is deterministic truncation at 1200 chars; structured summary fields (`key_facts`, `decisions`, etc.) are stored as empty `[]`. Replace with LLM-backed structured summarization before analytics/billing workflows rely on these fields. |
| F32 | Low | `datetime.now()` used in test helpers; columns lack `timezone=True`. Schedule timezone audit pass. |
| F38 | High | Usage recorder is a stub; `UsageRecord` is dropped and never persisted to `llm_call_events`. Must be wired before billing/admin workflows. |
| F22 | Architecture | Manager routing output must be structured (no comma-split parser fallback in production orchestrator path). Required before Gate B (orchestrator mode). |

## Week 4 Entry Gates (Required Order)

1. **F35 resolved**: shared room-ownership guard extracted before any new route group is added.
2. **F36 resolved**: turn index sequencing safe under concurrent creation.
3. **F38 wired**: `UsageRecord` → `llm_call_events` DB persistence live before usage ledger work begins.
4. Only then begin Week 4 feature implementation.

## Recommended Week 4 Build Order

1. Resolve F35 + F36 + F32 carryovers (code quality/correctness gate).
2. Wire `llm_call_events` persistence: complete `UsageRecorder`, add `pricing_version` to `llm_call_events` model, apply migration (F38).
3. LangGraph integration baseline: Postgres checkpointer, single-graph-per-turn runner.
4. Manual mode execution path: tag parsing → single tagged-agent dispatch → turn write.
5. Round Table mode execution path: ordered all-agent dispatch → partial-failure continuation.
