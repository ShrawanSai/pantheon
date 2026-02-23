# Pantheon MVP - Sprint Week 4 Checklist

Sprint window: Week 4 (Usage Ledger + LangGraph + Manual/Round Table Modes)
Owner: Codex
Reviewer: External supervising engineer
Last updated: 2026-02-21

## Sprint Goal
Close all Week 3 carryover blockers, wire the usage ledger to persistent storage, integrate LangGraph as the execution runtime, and deliver the first two interaction modes (Manual and Round Table) with full turn-write coverage.

## Definition of Done (Week 4)
- F35, F36, F38 carryovers resolved before any new route or interaction-mode code is added.
- `llm_call_events` is persisted to DB with pricing version on every turn execution.
- LangGraph runs as the execution engine for at least one mode (Manual).
- Manual mode executes correctly: tagged agent only, no-valid-tag validation error, turn written.
- Round Table mode executes correctly: all agents respond in order, partial-failure continuation, turn written.

## Tracking Rules
- Every task has an ID and status.
- Status values: `TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`.
- After each completed task, update:
  1. Task status
  2. Evidence/notes
  3. Change log entry

## Supervisor Checkpoint Rule
- Stop for supervisor review after each task that includes:
  1. Persistent storage changes to billing/usage ledger
  2. New execution runtime integration (LangGraph)
  3. New interaction mode execution paths

## Dependency Rules (Critical Path)
- W4-01 → W4-02 → W4-03 (carryover gates must clear before feature work)
- W4-03 → W4-04 → W4-05
- W4-04 and W4-05 may overlap if LangGraph integration (W4-03) is stable

## Week 4 Task Checklist

| ID | Task | Status | Acceptance Criteria | Evidence / Notes |
|---|---|---|---|---|
| W4-01 | Resolve F35 + F36 + F32 carryovers | DONE | `_get_owned_active_room_or_404` extracted to shared module; `turn_index` creation handles `IntegrityError` or uses a safe sequencing strategy; `datetime.now(timezone.utc)` used consistently with timezone-aware columns | Added shared guard `apps/api/app/dependencies/rooms.py:get_owned_active_room_or_404` and switched `rooms.py`/`sessions.py` to use it (F35). Added `IntegrityError` handling in session turn write path (`flush` + `commit`) to return `409` conflict message on concurrent turn index collisions (F36). Added timezone migration `infra/alembic/versions/20260221_0005_timezone_columns.py`, updated ORM `DateTime(..., timezone=True)` columns, updated test helpers to UTC-aware timestamps, and applied staging DB upgrade to `20260221_0005 (head)` (F32). Validation: `unittest` 31/31 pass, Ruff critical rules pass. |
| W4-02 | Wire `llm_call_events` persistence (F38) | DONE | `UsageRecorder.record_llm_usage` writes a row to `llm_call_events`; row includes `pricing_version`, all OE fields, and FK references; migration applied; `FakeUsageRecorder` in tests still verifiable via `records` list | Implemented `LlmCallEvent` ORM model in `apps/api/app/db/models.py` and rewired `UsageRecorder.record_llm_usage(db, record)` to persist usage rows with pricing/version + OE/credit fields in `apps/api/app/services/usage/recorder.py`. Turn route now passes `db` and `room_id` into `UsageRecord` (`apps/api/app/api/v1/routes/sessions.py`). Added route-level persistence test `test_create_turn_persists_llm_call_event_with_pricing_version` in `tests/test_sessions_routes.py` (uses real recorder, verifies `pricing_version=2026-02-20`, provider/model/status and room FK). Existing fake recorder override remains compatible and verifiable via `.records` list in other tests. Migration chain already includes `llm_call_events` (`20260221_0003`), staging confirmed at `20260221_0005 (head)`. |
| W4-03 | LangGraph integration baseline | DONE | Postgres checkpointer configured; single-graph-per-turn runner implemented; graph state definition for turn execution documented; existing turn path refactored to run through LangGraph graph | Added LangGraph runner service in `apps/api/app/services/orchestration/mode_executor.py` with typed state (`TurnExecutionState`), single-node graph (`call_model`), and per-turn `ainvoke` path (`run_turn`). Checkpointer baseline supports Postgres saver when package/runtime is available and falls back to `MemorySaver` for local/test determinism. Refactored `POST /api/v1/sessions/{session_id}/turns` in `apps/api/app/api/v1/routes/sessions.py` to execute model calls via `LangGraphModeExecutor` instead of direct gateway calls. Added graph state/flow design note in `docs/week4_langgraph_baseline.md`. Added `tests/test_langgraph_mode_executor.py` and updated route tests with `get_mode_executor` override. Validation: `unittest` 33/33 pass, Ruff critical checks pass. |
| W4-04 | Manual mode execution path | DONE | Tag parser extracts `@agent_key` mentions from user input; tagged agents only are dispatched; no-valid-tag input returns `422` validation error (not silent skip); turn and messages written; at least 3 route-level tests covering tagged dispatch, untagged rejection, and unknown-tag rejection | Added manual/tag dispatch support in `POST /api/v1/sessions/{session_id}/turns` (`apps/api/app/api/v1/routes/sessions.py`): parses `@agent_key` tags, requires at least one valid room agent tag in `manual`/`tag` modes, selects first valid tagged agent by message tag order for MVP, and returns `422` with structured error code when tags are absent/invalid. Added route-level tests in `tests/test_sessions_routes.py`: `test_manual_mode_dispatches_only_tagged_agent`, `test_manual_mode_rejects_untagged_message`, `test_manual_mode_rejects_unknown_tag`, and `test_manual_mode_with_multiple_tags_uses_first_valid_match_only`. Validation: `.\\.venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_*.py"` => `37/37` pass; `.\\.venv\\Scripts\\python.exe -m ruff check apps tests --select E9,F63,F7,F82` => pass. |
| W4-05 | Round Table mode execution path | DONE | All agents in room execute sequentially by `position`; each agent receives earlier same-turn outputs in context; one agent failure marks turn as `partial` and continues remaining agents; final turn written; at least 3 route-level tests covering ordered dispatch, partial-failure continuation, and full-success path | Implemented round table path in `apps/api/app/api/v1/routes/sessions.py`: selects all room agents by `position`, executes each sequentially through `LangGraphModeExecutor`, appends prior same-turn outputs into downstream agent context, stores one assistant message per agent, and marks turn `partial` with structured `[[agent_error]]` content when an agent fails while continuing remaining agents. Added route-level tests in `tests/test_sessions_routes.py`: `test_roundtable_mode_dispatches_agents_in_position_order`, `test_roundtable_mode_full_success_writes_all_assistant_messages`, and `test_roundtable_mode_partial_failure_continues_remaining_agents`. Post-review fix applied: single-agent modes include exact `Agent role:` in budgeted system messages, while roundtable intentionally omits per-agent role prompts from budget `system_messages` to avoid cross-agent instruction contamination (actual role prompts are still injected per-agent at execution time). Validation: `.\\.venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_*.py"` => `40/40` pass; `.\\.venv\\Scripts\\python.exe -m ruff check apps tests --select E9,F63,F7,F82` => pass. |

## Current Focus
- Active task: Week 4 closed (handoff published)
- Next after active: Week 5 kickoff (`docs/sprint_week5_checklist.md`)

## Assumptions And Follow-Ups
- F37 (Context Quality): structured summarization (LLM-backed) is deferred until after Round Table mode is stable; empty `[]` fields in `session_summaries` are acceptable through Week 4.
- F22 (Architecture): structured output contract for orchestrator manager routing is required before Week 5 (Orchestrator mode). Week 4 does not implement orchestrator mode.
- Pricing model: `pricing_version` schema locked at `2026-02-20` from master plan; version field must be stored per `llm_call_events` row for future repricing.
- LangGraph: Week 4 baseline uses Postgres checkpointer only; no HITL interrupt hooks needed yet (design keeps them non-blocking for future).
- Round Table partial-failure: failed agent response is stored as an error-annotated message (role `assistant`, agent name present, content is structured error annotation); turn status set to `partial`.
- F39 (Testing): `IntegrityError` -> `409` conflict path in turn creation is implemented but not yet route-tested with a deterministic collision harness.
- F40 (Migration Drift): `infra/alembic/versions/20260221_0003_llm_call_events.py` declares `step_id -> turn_steps.id` FK, but `turn_steps` is not present in migrations `0001`-`0005`. Remove/patch this FK before the next clean environment provision; add back only when `turn_steps` table exists.
- F41 (Billing Hardening): usage event persistence currently commits in a second transaction after turn commit. If usage commit fails, turn can exist without `llm_call_events` row. Before billing launch, move to single transaction or add deterministic reconciliation.
- F42 (Ops Observability): `_build_checkpointer()` currently falls back to `MemorySaver` without structured warning telemetry when Postgres checkpointer initialization fails.
- F43 (Ops Setup): Postgres checkpointer path requires one-time checkpoint table setup before production/staging traffic uses it (`PostgresSaver.setup()` or equivalent schema migration).
- F44 (Manual Mode Scope): manual/tag mode is intentionally single-agent-per-turn in MVP; multiple valid tags currently dispatch only the first valid tagged agent in message order. Full multi-tag fan-out is deferred.

## Change Log
- 2026-02-21: Initialized Week 4 checklist from Week 3 handoff. Gate-first order locked: F35/F36/F38 must close before W4-03 begins.
- 2026-02-21: Completed W4-01 carryover gate. Extracted shared room ownership dependency (`apps/api/app/dependencies/rooms.py`), added turn conflict handling (`IntegrityError` -> 409) in `sessions.py`, standardized UTC timestamp writes in API paths, converted datetime columns to timezone-aware (`20260221_0005` migration), and aligned timestamp test helpers to UTC-aware values. Validation pass: `unittest` 31/31, Ruff critical checks pass.
- 2026-02-21: Logged F39 follow-up for missing deterministic test coverage of the `IntegrityError` -> `409` turn-conflict response path.
- 2026-02-21: Completed W4-02 (F38). Usage recorder now persists `llm_call_events` rows through ORM with `pricing_version` and OE/credit fields; added route-level DB assertion test for persisted usage event. Validation pass: `unittest` 32/32, Ruff critical checks pass. Staging migration state confirmed `20260221_0005 (head)`.
- 2026-02-21: Added supervisor-raised follow-ups after W4-02 review: F40 (migration FK drift on `step_id -> turn_steps.id`) and F41 (usage persistence commit split from turn transaction).
- 2026-02-21: Completed W4-03 LangGraph baseline. Introduced `LangGraphModeExecutor` with single-node graph execution and checkpointer fallback strategy, refactored session turn route to call the graph runner, documented graph state contract (`docs/week4_langgraph_baseline.md`), and added LangGraph executor test coverage. Validation pass: `unittest` 33/33, Ruff critical checks pass.
- 2026-02-21: Added supervisor-raised follow-ups after W4-03 review: F42 (checkpointer fallback observability) and F43 (Postgres checkpointer table setup prerequisite).
- 2026-02-21: Completed W4-04 manual mode execution path. Added `@agent_key` parser + strict manual/tag mode validation and tagged-agent dispatch in session turn route; added three route-level tests for tagged success and no-valid-tag failures. Validation pass: `unittest` 36/36, Ruff critical checks pass.
- 2026-02-21: Resolved W4-04 scope flag by locking manual/tag mode to single-agent-per-turn for MVP, documenting this in `docs/week4_langgraph_baseline.md`, adding follow-up F44, and adding explicit multi-tag behavior test (`test_manual_mode_with_multiple_tags_uses_first_valid_match_only`).
- 2026-02-21: Completed W4-05 round table mode execution path. Added sequential multi-agent execution in `roundtable` mode with same-turn output carry-forward context, per-agent assistant message persistence, and partial-failure continuation/error annotation handling. Added three route-level roundtable tests for ordered dispatch, full success, and partial failure continuation. Validation pass: `unittest` 40/40, Ruff critical checks pass.
- 2026-02-21: Resolved W4-05 re-check flag by removing cross-agent role prompt injection from roundtable budget messages; single-agent modes keep exact role-prompt budgeting, and roundtable keeps per-agent role prompts only at execution time to prevent conflicting system instructions.
- 2026-02-21: Week 4 closeout complete. Published `docs/sprint_week4_handoff.md` and initialized `docs/sprint_week5_checklist.md`.
