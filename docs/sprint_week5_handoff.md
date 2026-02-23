# Pantheon MVP - Sprint Week 5 Handoff

Date: 2026-02-22  
Owner: Codex  
Reviewer: External supervising engineer

## Sprint Goal
Harden reliability gaps from Week 4 and complete orchestrator/summary/billing consistency foundations needed before Week 6 feature expansion.

## Completion Snapshot
- W5-01 through W5-06: complete.
- Validation status:
  - `unittest`: `51/51` passing
  - `ruff` critical rules (`E9,F63,F7,F82`): passing
- Staging status at close:
  - API health verified (`GET /api/v1/health` -> `200`)
  - Turn execution verified with authenticated requests (`201`)
  - DB migration head: `20260222_0006`

## Delivered Artifacts

### W5-01 - F42 + F43 Checkpointer Readiness
Added checkpointer observability and setup behavior in `apps/api/app/services/orchestration/mode_executor.py`: warning logs on fallback to `MemorySaver`, info logs when Postgres checkpointer is active, and a one-time `setup()` hook. Added test coverage in `tests/test_langgraph_mode_executor.py` for fallback warning behavior and setup-once behavior. Added staging runbook `docs/week5_checkpointer_setup.md`.

### W5-02 - F40 Migration Drift Fix (`turn_steps` / `step_id` FK)
Authored and applied migration `infra/alembic/versions/20260222_0006_drop_turn_steps.py` (`down_revision=20260221_0005`) to drop `llm_call_events_step_id_fkey` and remove unused `turn_steps` table/index. Verified on staging: `to_regclass('public.turn_steps')` is `NULL` and `llm_call_events_step_id_fkey` no longer exists for `step_id`.

### W5-03 - F39 Deterministic Conflict-Path Test
Added deterministic `409` conflict test `test_create_turn_returns_409_on_duplicate_turn_index` in `tests/test_sessions_routes.py` using `ConflictInjectingModeExecutor`. The injector stages a conflicting turn in the same DB session before route flush, guaranteeing an `IntegrityError` without real concurrency.

### W5-04 - F22 Structured Orchestrator Routing
Added `apps/api/app/services/orchestration/orchestrator_manager.py` with frozen `OrchestratorRoutingDecision` and `route_turn()` JSON-contract manager routing. Wired `create_turn` orchestrator branch to use manager routing via injected `llm_gateway` and `ORCHESTRATOR_MANAGER_MODEL_ALIAS`. Added `tests/test_orchestrator_manager.py` (3 unit tests) and route-level orchestrator selection test in `tests/test_sessions_routes.py`.

### W5-05 - F37 Structured Summary Output
Added `apps/api/app/services/orchestration/summary_extractor.py` with `SummaryStructure` and strict JSON extraction contract. Wired `create_turn` summary persistence to populate `key_facts_json`, `decisions_json`, `open_questions_json`, and `action_items_json` from extractor output instead of hardcoded `[]`. Added `SUMMARIZER_MODEL_ALIAS` config and `tests/test_summary_extractor.py` (valid JSON, invalid JSON fallback, missing-key fallback).

### W5-06 - F41 Billing/Usage Consistency
Implemented single-transaction usage persistence model. Added `stage_llm_usage(db, record)` in `apps/api/app/services/usage/recorder.py` (no commit) and moved usage staging before the route’s main commit in `apps/api/app/api/v1/routes/sessions.py`. Kept `record_llm_usage` backward-compatible (`stage + commit`). Added atomicity test `test_create_turn_usage_committed_atomically_with_turn` confirming `Turn` and `LlmCallEvent` persist together.

## Runtime Capability At Close
Compared to Week 4 close, the system now additionally supports:
- Observable and setup-aware checkpointer startup behavior.
- Clean schema without unused `turn_steps` drift.
- Deterministic test coverage for turn-index conflict response contract.
- Structured orchestrator manager routing with typed decisions and safe fallback behavior.
- Structured summary extraction persistence into all four summary JSON fields.
- Single-transaction turn + usage persistence, eliminating partial-commit billing gaps.

## Carry-Forward Follow-Ups (Week 6+)

| ID | Severity | Description |
|---|---|---|
| F44 | Medium | Manual/tag mode remains single-agent-per-turn for MVP; multi-tag fan-out still deferred. |
| F45 | Low | Roundtable budget intentionally omits per-agent role prompt in shared budget messages to avoid cross-agent contamination; slight budget undercount remains accepted tradeoff. |
| F46 | Medium | Orchestrator manager routing LLM call is currently treated as system overhead and not separately metered/billed. Decide if manager-call metering is required for admin cost accounting. |
| F47 | Medium | `record_llm_usage` is retained for backward compatibility; new route path uses `stage_llm_usage`. Audit external callers and migrate to staged/transactional pattern where appropriate. |
| F48 | Low | Routing/extraction helper calls use fixed token caps (`256` manager, `512` summary extractor). Consider moving to settings if routing/summarization complexity increases. |

## Week 6 Entry Gates
1. Confirm Week 5 closure artifacts are approved (this handoff + checklist).
2. Decide whether manager routing usage (F46) should be metered before scaling orchestrator traffic.
3. Lock transaction-boundary policy for all future write paths to preserve F41 guarantees.

## Recommended Week 6 Build Order
1. Finalize Week 5 closure (`W5-07`) and open Week 6 checklist.
2. Address metering policy for orchestrator manager calls (F46) and align pricing docs.
3. Expand orchestrator execution behavior beyond single-agent routing (if in scope).
4. Continue summary quality improvements (LLM generation quality/consistency), keeping extractor contract stable.
5. Audit all usage write paths for staged single-transaction behavior (F47 cleanup).
6. Revisit manual/tag multi-agent fan-out (F44) if UX/business scope prioritizes it.
