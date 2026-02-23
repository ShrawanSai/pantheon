# Pantheon MVP - Sprint Week 6 Checklist

Sprint window: Week 6 (Orchestrator Expansion + Summary Quality + Usage Hygiene)  
Owner: Codex  
Reviewer: External supervising engineer  
Last updated: 2026-02-22

## Sprint Goal
Execute Week 6 feature work in a gate-first order: lock metering and transaction policy decisions, eliminate legacy usage-write drift, then expand orchestrator and summary behavior without regressing reliability.

## Definition of Done (Week 6)
- F46 policy is explicitly decided and documented before orchestrator expansion starts.
- Transaction-boundary policy is published and followed by all new write paths.
- F47 audit is complete and all in-scope callers use staged single-transaction write behavior.
- Orchestrator expansion ships with typed contracts, strict JSON parsing, and logged fallbacks.
- Summary quality improvements preserve extractor contract stability.
- LLM helper parsing uses Pydantic `BaseModel.model_validate_json()` contracts instead of manual `json.loads()` parsing.
- Week 6 handoff doc is published with test counts, staging evidence, and carry-forward risks.

## Entry Gates (Must Resolve Before First Feature Task)
1. F46 policy decision recorded in writing:
   - Option A: meter manager-routing calls as system overhead in admin cost reports.
   - Option B: treat manager-routing calls as free infrastructure (unmetered).
2. Transaction-boundary policy locked in `docs/transaction_policy.md`.
3. Supervisor confirms Week 6 start after (1) and (2).

## Tracking Rules
- Every task has an ID and status.
- Status values: `TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`.
- After each task state change, update:
  1. status
  2. evidence/notes
  3. changelog entry

## Supervisor Checkpoint Rule
- Stop for supervisor review after each task that changes:
  1. orchestration/runtime behavior
  2. migration/schema behavior
  3. billing/usage consistency behavior

## Staging Evidence Rule
- Staging evidence is required to close any task that touches:
  1. migration behavior
  2. auth behavior
  3. new runtime execution behavior
- Local test pass is necessary but not sufficient for those task types.

## Test Accounting Rule
- State test count at each task close.
- If test count drops or remains flat where coverage should increase, flag before `DONE`.

## Migration Rule
- Confirm `down_revision` against current staging head before authoring migration.
- Confirm live constraint/index names from the database before hardcoding names in migration files.

## Technical Patterns Locked In
- Use typed frozen dataclasses for inter-service contracts.
- Use strict JSON contracts with logged fallback for every LLM helper parser.
- Respect `db.flush()` vs `db.commit()` distinction:
  - flush detects integrity conflicts early
  - commit makes writes durable
- Keep `FakeManagerGateway` default response as `"not json"` unless test explicitly sets valid content.

## Dependency Rules (Critical Path)
- W6-01 -> W6-02 -> W6-04
- W6-03 can run in parallel after W6-01 policy lock
- W6-05 depends on explicit F44 scope decision
- W6-07 runs after runtime changes are complete (W6-03/W6-05/W6-06)
- W6-08 depends on completion or explicit deferral notes for all W6 tasks

## Week 6 Task Checklist

| ID | Task | Status | Acceptance Criteria | Evidence / Notes |
|---|---|---|---|---|
| W6-01 | Lock entry-gate decisions (F46 + transaction policy) | DONE | F46 decision written and approved; `docs/transaction_policy.md` published; supervisor confirms gate clear | F46 locked: Option 2 (`unmetered infrastructure`) per product decision. Trigger to revisit: orchestrator traffic reaches meaningful scale or stakeholders require admin overhead reporting. Transaction policy published at `docs/transaction_policy.md`. Gate cleared for Week 6 feature work. |
| W6-02 | Close F47 (audit + migrate `record_llm_usage` callers) | DONE | All in-scope write paths audited; route-level usage writes use staged pattern; legacy direct-commit usage calls either removed or explicitly justified; tests updated | Completed repository audit with `rg`. Results: no route/service caller invokes `record_llm_usage`; active route path in `apps/api/app/api/v1/routes/sessions.py` uses `stage_llm_usage` before single commit. `record_llm_usage` remains only as compatibility wrapper in `apps/api/app/services/usage/recorder.py` and in test fake method for compatibility coverage. F47 is closed for current scope. Validation: `.\\.venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_*.py"` => `51/51` pass; `.\\.venv\\Scripts\\python.exe -m ruff check apps tests --select E9,F63,F7,F82` => pass. |
| W6-03 | Orchestrator execution expansion (post-F46) | DONE | Expanded orchestrator behavior implemented under typed contracts with strict JSON fallback behavior and tests | Supervisor approved. Ordered orchestrator plan routing shipped via `selected_agent_keys` JSON contract with backward-compatible single-key support and deterministic fallback behavior. Route executes manager-selected sequence with same-turn context propagation and multi-agent persistence support. Validation: `.\\.venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_*.py"` => `53/53` pass; Ruff critical checks pass. |
| W6-04 | Summary quality improvements (extractor contract stable) | DONE | Summary quality improved without breaking `SummaryStructure` schema/route persistence contract; tests verify both valid and fallback behaviors | Supervisor approved. Added `apps/api/app/services/orchestration/summary_generator.py` with strict JSON contract (`{\"summary_text\":\"...\"}`) and deterministic logged fallback. `sessions.py` now runs two-stage summary pipeline (`generate_summary_text` -> `extract_summary_structure`) while preserving existing extractor schema/persistence contract. Added `tests/test_summary_generator.py` with valid JSON, invalid JSON fallback, and missing-key fallback coverage. Validation: `.\\.venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_*.py"` => `56/56` pass; `.\\.venv\\Scripts\\python.exe -m ruff check apps tests --select E9,F63,F7,F82` => pass. |
| W6-05 | F44 scope decision and implementation (multi-tag fan-out or defer) | DONE | Scope choice documented before implementation; if implemented, tests cover order + billing/usage expectations; if deferred, deferral rationale logged | Supervisor approved. Scope locked to implement now: manual/tag multi-tag fan-out enabled in `sessions.py` (all valid tagged agents dispatched in tag order). Updated test `test_manual_mode_with_multiple_tags_dispatches_all_valid_tags_in_order` asserts ordered dispatch (`qwen`, `deepseek`) and combined assistant output includes both agent names. Validation: `.\\.venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_*.py"` => `56/56` pass; `.\\.venv\\Scripts\\python.exe -m ruff check apps tests --select E9,F63,F7,F82` => pass. |
| W6-06 | Pydantic structured-output refactor for LLM helper parsers | DONE | `orchestrator_manager.py`, `summary_extractor.py`, and `summary_generator.py` use internal Pydantic parse models + `model_validate_json()`; manual JSON parsing helpers removed; fallback behavior preserved; tests green | Supervisor approved. Implemented internal parse models: `_RoutingResponse`, `_ExtractionResponse`, `_GenerationResponse`. Replaced manual `json.loads()` + type/key checks with `model_validate_json()` in all three modules. Removed manual parser helpers and retained domain dataclass contracts. `SummaryExtractor` missing-key behavior now defaults silently via model defaults. Updated tests accordingly (`test_extract_defaults_missing_keys_without_fallback_warning`). Validation: `.\\.venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_*.py"` => `56/56` pass; `.\\.venv\\Scripts\\python.exe -m ruff check apps tests --select E9,F63,F7,F82` => pass. |
| W6-07 | Staging validation for Week 6 runtime/migration changes | DONE | Staging logs/endpoints demonstrate expected runtime behavior; migration/auth/runtime changes validated with evidence snapshots | Completed authenticated staging verification from CLI. Evidence: `GET /api/v1/health` => `200`; `GET /api/v1/auth/me` succeeded; manual fan-out turn completed (`turn_id=2bcf4f39-e469-41e2-ad74-a945931b3d25`) with both `Writer:` and `Researcher:` in `assistant_output`; orchestrator turn completed (`turn_id=8e04c42d-479b-4dae-bbf3-a47fae926d7e`); summary runtime path validated with `summary_triggered=true` in staging session `70fdf176-5dd6-4294-af59-5b7bdc3e66f2` after 9 turns (`last_turn_id=61d62494-62d6-48b3-9268-606aa79bc447`). No 5xx responses observed during flow. |
| W6-08 | Week 6 handoff document | DONE | `docs/sprint_week6_handoff.md` published with completion snapshot, artifacts, carry-forward items, Week 7 gates/order | Handoff finalized at `docs/sprint_week6_handoff.md` with all required sections, validated staging evidence, and Alembic head confirmation (`20260222_0006`). Supervisor approved; Week 6 formally closed. |

## Current Focus
- Active task: Week 6 closed
- Next after active: Week 7 kickoff planning

## Assumptions And Follow-Ups
- F46 locked for Week 6: manager routing calls are unmetered infrastructure (not user-billed and not admin-overhead metered yet). Revisit after F47 if orchestrator traffic scales or stakeholder reporting requires overhead categorization.
- F49 (carry-forward): for multi-agent orchestrator turns, response-level `model_alias_used` and `TurnContextAudit.model_alias` currently reflect first selected agent semantics, which can under-represent multi-agent usage context.
- F50 (carry-forward): add orchestrator-sequence partial-failure route test coverage (one agent fails mid-sequence, turn status `partial`, continuation verified).
- F51 (carry-forward): `SummaryGenerationResult.used_fallback` is currently not consumed in route-level audit/logging; consider capturing this signal in ops/audit telemetry.
- F52 (carry-forward): if parse-error observability needs reduction, consider trimming verbose Pydantic validation text in warning logs for non-debug environments.
- F45 remains accepted tradeoff unless product changes roundtable billing model.
- F48 remains low-priority unless new routing/extraction callers are added this sprint.
- Week 6 must preserve single-transaction staged-write guarantees established in Week 5.
- Any deviation from transaction policy requires explicit supervisor sign-off and doc note.

## Change Log
- 2026-02-22: Initialized Week 6 checklist from `docs/sprint_week5_handoff.md`, supervisor guidance, and Week 6 sprint governance notes. Set W6-01 as active gate task.
- 2026-02-22: Closed W6-01. Locked F46 to Option 2 (unmetered manager routing infrastructure) and published transaction-boundary policy at `docs/transaction_policy.md`.
- 2026-02-22: Closed W6-02. Completed F47 caller audit; verified route-level usage writes are staged (`stage_llm_usage`) and no in-scope runtime caller uses `record_llm_usage` directly.
- 2026-02-22: Added W6-02 validation evidence (`unittest` 51/51 pass; Ruff critical checks pass) and moved W6-03 to `IN_PROGRESS`.
- 2026-02-22: Implemented W6-03 orchestrator execution expansion (ordered manager-selected agent sequence with strict JSON fallback behavior) and added test coverage. Local validation: `unittest` 53/53 pass; Ruff critical checks pass. Awaiting supervisor review.
- 2026-02-22: Closed W6-03 after supervisor approval and logged carry-forward observations F49/F50.
- 2026-02-22: Started W6-04. Added strict-JSON summary generation helper (`summary_generator.py`) with logged fallback, wired improved summary text generation into session summary persistence before structured extraction, and added generator unit tests. Local validation: `unittest` 56/56 pass; Ruff critical checks pass.
- 2026-02-22: Closed W6-04 after supervisor approval; logged F51 carry-forward (`used_fallback` telemetry not yet consumed) and moved W6-05 to `IN_PROGRESS`.
- 2026-02-22: W6-05 scope decision locked to implement F44 multi-tag fan-out now. Updated manual/tag dispatch to execute all valid tagged agents in tag order and updated multi-tag test coverage. Local validation: `unittest` 56/56 pass; Ruff critical checks pass. Awaiting supervisor review.
- 2026-02-22: Closed W6-05 after supervisor approval.
- 2026-02-22: Started W6-06 (Pydantic parser refactor). Replaced manual JSON parse logic with `BaseModel.model_validate_json()` in orchestrator/summary helper modules, updated extractor missing-key behavior to default silently via typed model defaults, and updated tests. Local validation: `unittest` 56/56 pass; Ruff critical checks pass. Awaiting supervisor review.
- 2026-02-22: Closed W6-06 after supervisor approval and moved W6-07 to `IN_PROGRESS`.
- 2026-02-22: W6-07 partial verification complete from CLI: staging health endpoint `https://api-staging-3c02.up.railway.app/api/v1/health` returned `200`. Awaiting authenticated runtime evidence/logs for full closure.
- 2026-02-22: Closed W6-07 with authenticated staging evidence from CLI. Verified health/auth success, manual multi-tag fan-out runtime behavior, orchestrator runtime behavior, and summary-trigger runtime path (`summary_triggered=true`) with no 5xx responses observed.
- 2026-02-22: Moved W6-08 to `IN_PROGRESS` for handoff drafting.
- 2026-02-22: Drafted `docs/sprint_week6_handoff.md` and added staging migration-head confirmation (`20260222_0006`) in completion snapshot. Awaiting supervisor review for W6-08 closure.
- 2026-02-22: Closed W6-08 after supervisor approval. Week 6 is formally closed.
