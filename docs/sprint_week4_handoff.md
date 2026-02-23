# Pantheon MVP - Sprint Week 4 Handoff

Date: 2026-02-21  
Owner: Codex  
Reviewer: External supervising engineer

## Sprint Goal
Close Week 3 carryovers, persist usage ledger events, integrate LangGraph execution, and ship Manual + Round Table interaction modes with DB-backed turn writes.

## Completion Snapshot
- W4-01 through W4-05: complete.
- Validation status:
  - `unittest`: `40/40` passing
  - `ruff` critical rules (`E9,F63,F7,F82`): passing
- Staging status at close:
  - API and worker deployed and healthy
  - Staging DB at `20260221_0005 (head)`

## Delivered Artifacts

### Carryover Gates (W4-01)
- F35 resolved: shared room ownership dependency extracted to `apps/api/app/dependencies/rooms.py`.
- F36 resolved: turn-write conflict path returns `409` on `IntegrityError`.
- F32 resolved: timezone-aware timestamps standardized in API write paths and models; timezone migration applied (`20260221_0005_timezone_columns.py`).

### Usage Ledger Persistence (W4-02)
- `UsageRecorder.record_llm_usage(db, record)` now persists to `llm_call_events`.
- `LlmCallEvent` ORM model added to `apps/api/app/db/models.py`.
- `PRICING_VERSION` config added and persisted per call event.
- Route-level persistence test added (`test_create_turn_persists_llm_call_event_with_pricing_version`).

### LangGraph Baseline (W4-03)
- `apps/api/app/services/orchestration/mode_executor.py` added:
  - `TurnExecutionState`
  - `TurnExecutionInput` / `TurnExecutionOutput`
  - single-node graph (`call_model -> END`)
  - checkpointer baseline with Postgres saver + MemorySaver fallback
- Turn route refactored to run LLM calls through mode executor.
- Baseline design captured in `docs/week4_langgraph_baseline.md`.

### Manual Mode (W4-04)
- `@agent_key` parser added.
- Manual/tag mode enforces at least one valid tagged agent.
- Manual/tag mode dispatches first valid tagged agent (MVP scope), tracked as F44.
- Added route tests for:
  - tagged dispatch success
  - untagged rejection (`422`)
  - unknown-tag rejection (`422`)
  - multi-tag first-valid behavior

### Round Table Mode (W4-05)
- Roundtable dispatch executes all agents sequentially by `position`.
- Same-turn carry-forward context implemented: later agents see earlier agent outputs/errors.
- Partial-failure continuation implemented:
  - failed agent recorded as `[[agent_error]] ...`
  - turn status set to `partial`
  - remaining agents continue execution
- Per-agent assistant messages persisted.
- Role-prompt contamination fix applied:
  - single-agent modes include role prompt in budgeted system messages
  - roundtable omits budget-role prompt from shared system messages
  - per-agent role prompt is injected only per loop execution
- Added route tests for:
  - ordered dispatch
  - full-success roundtable write
  - partial-failure continuation

## Runtime Capability At Close
- Room/session/turn stack now supports:
  - manual/tag mode execution
  - roundtable mode execution
  - context guardrails with audit trail
  - usage ledger persistence to `llm_call_events`
  - LangGraph-based model execution baseline

## Carry-Forward Follow-Ups (Week 5+)

| ID | Severity | Description |
|---|---|---|
| F22 | High | Orchestrator manager routing must use structured output before orchestrator mode ships. |
| F37 | High | Summarization still stores empty structured fields (`[]`); LLM-structured summarization deferred. |
| F39 | Medium | `IntegrityError -> 409` conflict path not covered with deterministic collision harness. |
| F40 | High | Migration drift: `0003` includes `step_id -> turn_steps.id` FK while `turn_steps` table is absent in current chain. |
| F41 | High | Usage event persistence uses a second commit after turn commit; requires single transaction or reconciliation before billing launch. |
| F42 | Medium | Checkpointer fallback to MemorySaver lacks warning telemetry. |
| F43 | High | Postgres checkpointer requires one-time table setup before production/staging traffic relies on it. |
| F44 | Medium | Manual/tag mode is single-agent-per-turn in MVP; multi-tag fan-out deferred. |

## Week 5 Entry Gates
1. Decide and implement checkpointer readiness path:
   - F42 warning logs on fallback
   - F43 Postgres checkpointer setup/bootstrapping
2. Resolve migration drift risk (F40) before next clean environment bootstrap.
3. Lock execution consistency plan for billing safety (F41) before paid billing rollout.

## Recommended Week 5 Build Order
1. W5-01: Close F42 + F43 (observability and checkpointer setup).
2. W5-02: Close F40 migration drift (safe patch plan + verification on staging).
3. W5-03: Add deterministic concurrency-conflict test harness for F39.
4. W5-04: Start orchestrator execution path with structured manager routing (F22).
5. W5-05: Begin structured summary output implementation to close F37.
6. W5-06: Decide/implement billing-commit safety strategy for F41.
