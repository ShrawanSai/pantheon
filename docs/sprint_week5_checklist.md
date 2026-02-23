# Pantheon MVP - Sprint Week 5 Checklist

Sprint window: Week 5 (Orchestrator Foundation + Reliability Hardening)  
Owner: Codex  
Reviewer: External supervising engineer  
Last updated: 2026-02-21

## Sprint Goal
Harden execution reliability from Week 4 outputs and establish orchestrator-mode foundation with structured routing contracts.

## Definition of Done (Week 5)
- F42 and F43 are closed: checkpointer fallback is observable and Postgres checkpointer setup is validated in staging.
- F40 migration drift is resolved with a verified clean bootstrap path.
- F39 deterministic conflict test exists for turn-write race behavior.
- Orchestrator baseline runs with structured manager routing contract (no free-form comma parsing).
- Week 5 handoff doc published with validation evidence and open risks.

## Tracking Rules
- Every task has an ID and status.
- Status values: `TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`.
- After each task state change, update:
  1. status
  2. evidence/notes
  3. changelog entry

## Supervisor Checkpoint Rule
- Stop for supervisor review after each task that changes:
  1. migration/schema behavior
  2. orchestration/runtime behavior
  3. billing/usage consistency behavior

## Dependency Rules (Critical Path)
- W5-01 -> W5-02 -> W5-04
- W5-03 can run in parallel with W5-02
- W5-05 starts only after W5-04 baseline is stable
- W5-06 can start after W5-02

## Week 5 Task Checklist

| ID | Task | Status | Acceptance Criteria | Evidence / Notes |
|---|---|---|---|---|
| W5-01 | Close F42 + F43 checkpointer readiness | DONE | `_build_checkpointer()` logs warning when falling back to `MemorySaver`; Postgres checkpointer setup path documented and executed once on staging; startup/runtime behavior verified with staging smoke | Implemented observability + setup hook in `apps/api/app/services/orchestration/mode_executor.py`: warning log on fallback to `MemorySaver`, info log on Postgres checkpointer activation, and one-time `setup()` call per process. Added tests in `tests/test_langgraph_mode_executor.py` to verify fallback warning behavior and setup-once behavior with injected fake Postgres saver. Added runbook `docs/week5_checkpointer_setup.md` with staging verification steps. Local validation: `.\\.venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_*.py"` => `42/42` pass; Ruff critical checks pass. Staging evidence: `GET /api/v1/health` returned `200`, and authenticated turn requests completed (`POST /api/v1/sessions/{session_id}/turns` => `201 Created`) with no checkpointer runtime errors in deploy logs. |
| W5-02 | Close F40 migration drift (`llm_call_events.step_id`) | DONE | Clean migration strategy defined and applied so clean bootstrap no longer references missing `turn_steps`; Alembic upgrade from base to head succeeds on fresh DB; ORM and migration chain consistent | Verified staging FK name via SQL (`information_schema` query): `llm_call_events_step_id_fkey`. Added migration `infra/alembic/versions/20260222_0006_drop_turn_steps.py` (`down_revision=20260221_0005`) with required order: `upgrade()` drops FK then drops `turn_steps` index/table; `downgrade()` recreates `turn_steps` (with `DateTime(timezone=True)`), recreates index, then recreates FK with explicit name. Applied on staging: `alembic upgrade head` reported `Running upgrade 20260221_0005 -> 20260222_0006`. Post-checks on staging: `SELECT to_regclass('public.turn_steps');` => `NULL` (`None` in SQLAlchemy output), and FK lookup for `llm_call_events_step_id_fkey` on `step_id` => `0` rows (`[]`). Regression validation: `.\\.venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_*.py"` => `42/42` pass. |
| W5-03 | Add deterministic F39 conflict-path test harness | DONE | Route-level or integration test deterministically triggers duplicate `(session_id, turn_index)` path and asserts `409` response contract | Added deterministic route test in `tests/test_sessions_routes.py`: `test_create_turn_returns_409_on_duplicate_turn_index` using `ConflictInjectingModeExecutor`. Injector parses `payload.thread_id` via `split(':', 2)`, uses the same `db` session passed by route, inserts conflicting `(session_id, turn_index)` row without flushing, and returns normal `TurnExecutionOutput` so the route's `await db.flush()` deterministically raises `IntegrityError` and returns `409`. Test asserts exact response body: `{\"detail\": \"Turn creation conflicted with concurrent writes. Please retry.\"}` and restores `get_mode_executor` override in `finally`. Validation: `.\\.venv\\Scripts\\python.exe -m unittest discover -s tests -p \"test_*.py\"` => `43/43` pass; Ruff critical checks pass. Supervisor review accepted and W5-03 closed. |
| W5-04 | Orchestrator mode structured-routing baseline (F22) | DONE | Introduce typed manager routing output contract; remove any free-form parsing assumptions; route executes selected agents deterministically and records turn/messages | Added `apps/api/app/services/orchestration/orchestrator_manager.py` with frozen `OrchestratorRoutingDecision` dataclass and `route_turn()` manager routing function. Manager prompt now requires strict JSON output (`{\"selected_agent_key\":\"<key>\"}`) and validates against available room agents; invalid JSON or unknown keys log warnings and deterministically fall back to `agents[0]`. Updated `create_turn` in `apps/api/app/api/v1/routes/sessions.py` to inject `llm_gateway` dependency and add explicit `orchestrator` mode branch that calls `route_turn(...)` and selects the routed agent. Added config field in `apps/api/app/core/config.py`: `orchestrator_manager_model_alias` (default `deepseek`). Added manager unit tests in `tests/test_orchestrator_manager.py` (valid JSON selection, invalid JSON fallback+warning, unknown key fallback+warning) and route-level test in `tests/test_sessions_routes.py` (`test_orchestrator_mode_routes_to_manager_selected_agent`). Validation: `.\\.venv\\Scripts\\python.exe -m unittest discover -s tests -p \"test_*.py\"` => `47/47` pass; Ruff critical checks pass. Supervisor review accepted and W5-04 closed. |
| W5-05 | Structured summary output foundation (F37) | DONE | Replace empty `[]` summary fields with structured LLM-derived content contract (`key_facts`, `decisions`, `open_questions`, `action_items`) for at least one execution path | Added `apps/api/app/services/orchestration/summary_extractor.py` with `SummaryStructure` dataclass and `extract_summary_structure(...)` using strict JSON prompt contract. On invalid JSON parse, function logs warning and returns empty structure; on missing keys, function logs warning and defaults missing fields to `[]` while preserving provided valid arrays. Added config field `summarizer_model_alias` in `apps/api/app/core/config.py` (default `deepseek`). Updated `apps/api/app/api/v1/routes/sessions.py` summary write path to call extractor and persist structured arrays into `key_facts_json`, `decisions_json`, `open_questions_json`, and `action_items_json` instead of hardcoded `[]`. Added unit tests in `tests/test_summary_extractor.py`: valid JSON path, invalid JSON fallback, missing-key fallback. Validation: `.\\.venv\\Scripts\\python.exe -m unittest discover -s tests -p \"test_*.py\"` => `50/50` pass; Ruff critical checks pass. Supervisor review accepted and W5-05 closed. |
| W5-06 | Billing consistency plan for F41 | DONE | Decide and implement one approach: single transaction for turn+usage write or deterministic reconciliation job; failure mode is test-covered and documented | Implemented single-transaction approach. `apps/api/app/services/usage/recorder.py` now adds `stage_llm_usage(db, record)` (stages `LlmCallEvent` via `db.add`, no commit) while preserving existing `record_llm_usage` (unchanged external behavior: stage + commit). Updated `apps/api/app/api/v1/routes/sessions.py` to stage usage entries before the main `await db.commit()` and removed post-commit usage commits, resulting in a single happy-path commit for Turn + Messages + Summary + Audit + LlmCallEvents. Updated fake recorder in `tests/test_sessions_routes.py` with `stage_llm_usage`. Added new atomicity test `test_create_turn_usage_committed_atomically_with_turn` asserting both `Turn` and `LlmCallEvent` exist after one successful turn. Validation: `.\\.venv\\Scripts\\python.exe -m unittest discover -s tests -p \"test_*.py\"` => `51/51` pass; Ruff critical checks pass. Supervisor review accepted and W5-06 closed. |
| W5-07 | Week 5 handoff document | DONE | `docs/sprint_week5_handoff.md` created with completion snapshot, validation evidence, carry-forward risks, and Week 6 recommended order | Published `docs/sprint_week5_handoff.md` with all required sections (Sprint Goal, Completion Snapshot, Delivered Artifacts W5-01..W5-06, Runtime Capability At Close, Carry-Forward Follow-Ups, Week 6 Entry Gates, Recommended Week 6 Build Order). Supervisor review approved with no required changes. |

## Current Focus
- Active task: Week 5 closed
- Next after active: Week 6 kickoff planning

## Assumptions And Follow-Ups
- Week 4 behavior remains the baseline: manual/tag mode single-agent-per-turn (F44), roundtable sequential continuation on partial failures.
- Week 5 does not introduce final billing UI/Stripe flows; this sprint is backend reliability and orchestration foundation.
- Any production-impacting migration must be proven on staging first.

## Change Log
- 2026-02-21: Initialized Week 5 checklist from Week 4 handoff and carry-forward follow-ups (F22, F37, F39, F40, F41, F42, F43, F44).
- 2026-02-21: Started W5-01. Added checkpointer fallback observability and one-time Postgres setup hook in `mode_executor.py`, added test coverage (`test_langgraph_mode_executor.py`), and added staging runbook (`docs/week5_checkpointer_setup.md`). Local validation pass: `unittest` 42/42, Ruff critical checks pass. Waiting for staging deployment/log verification to mark W5-01 DONE.
- 2026-02-22: Closed W5-01. Staging runtime verified with `GET /api/v1/health` (`200`) and authenticated turn execution (`201`) without checkpointer runtime errors; checklist advanced to W5-02.
- 2026-02-22: Started W5-02. Confirmed staging FK name `llm_call_events_step_id_fkey` and authored migration `20260222_0006_drop_turn_steps.py` to remove unused `turn_steps` + `step_id` FK drift with reversible downgrade.
- 2026-02-22: Closed W5-02. Applied migration `20260222_0006` on staging, verified `turn_steps` removed and `llm_call_events_step_id_fkey` absent, and confirmed no test regressions (`42/42` pass).
- 2026-02-22: Started W5-03. Added deterministic conflict-path test harness with `ConflictInjectingModeExecutor` and verified `409` contract on duplicate `(session_id, turn_index)` at route flush-time (`43/43` tests passing).
- 2026-02-22: Closed W5-03 after supervisor acceptance. Checklist advanced to W5-04 (F22 structured orchestrator routing).
- 2026-02-22: Started W5-04. Added structured orchestrator manager routing module with typed decision contract and deterministic fallback semantics, wired orchestrator branch in `create_turn`, added manager model alias config, and added 4 tests (3 manager unit + 1 route-level). Validation pass: `47/47` tests, Ruff critical checks pass.
- 2026-02-22: Closed W5-04 after supervisor acceptance. F22 structured orchestrator routing baseline complete; checklist advanced to W5-05.
- 2026-02-22: Started W5-05. Added `summary_extractor` service + summarizer model alias config and wired structured summary persistence into `SessionSummary` writes; added 3 extractor unit tests. Validation pass: `50/50` tests, Ruff critical checks pass.
- 2026-02-22: Closed W5-05 after supervisor acceptance. F37 structured summary extraction baseline complete; checklist advanced to W5-06.
- 2026-02-22: Started W5-06. Implemented single-transaction billing consistency path by staging `LlmCallEvent` before the route commit (`stage_llm_usage`) and added atomicity verification test (`Turn` + `LlmCallEvent` persisted together). Validation pass: `51/51` tests, Ruff critical checks pass.
- 2026-02-22: Closed W5-06 after supervisor acceptance. F41 billing/usage consistency gap resolved via single-transaction staging model; checklist advanced to W5-07.
- 2026-02-22: Started W5-07. Preparing `docs/sprint_week5_handoff.md` for supervisor closeout review.
- 2026-02-22: Closed W5-07 after supervisor approval. Week 5 sprint is formally closed.
