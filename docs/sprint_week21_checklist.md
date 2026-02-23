# Pantheon MVP - Sprint Week 21 Checklist

Sprint window: Week 21 (Cycle 7 Part 2 - Orchestrator Mode Completion)  
Owner: Codex  
Reviewer: External supervising engineer  
Last updated: 2026-02-23

## Sprint Goal
Complete orchestrator mode MVP behavior by adding manager synthesis after specialist outputs, unlocking orchestrator mode patching, and enforcing the single-round invocation cap guard.

## Baseline
- Local tests at sprint open: `190` passing.
- Migration head at sprint open: `20260223_0018`.

## Definition of Done
- Orchestrator turns generate a manager synthesis after specialist responses.
- Synthesis is persisted as a shared manager message and included in `Turn.assistant_output`.
- Synthesis usage is recorded and debited in the same transaction as the turn.
- Room mode patch endpoint allows `orchestrator` and rejects unknown modes with updated guard text.
- Orchestrator specialist invocation is capped at 3 (belt-and-suspenders guard in both turn paths).
- Week 21 handoff is published.

## Week 21 Task Checklist
| ID | Task | Status | Acceptance Criteria | Evidence / Notes |
|---|---|---|---|---|
| W21-01 | Manager synthesis function | DONE | `generate_orchestrator_synthesis(...)` added with manager prompt + specialist output folding; skips empty specialist list | Added in `apps/api/app/services/orchestration/orchestrator_manager.py` with `OrchestratorSynthesisResult` and shared prompt builder `build_orchestrator_synthesis_messages(...)`. |
| W21-02 | Wire synthesis into both turn paths | DONE | Non-stream and stream orchestrator paths add synthesis, persist manager message, and stage extra usage/debit in same commit | Wired in `apps/api/app/api/v1/routes/sessions.py` for both `create_turn` and `create_turn_stream`; synthesis block appended to `assistant_output`; manager `Message` persisted (`source_agent_key="manager"`). |
| W21-03 | Mode patch unlock + invocation cap | DONE | `PATCH /rooms/{room_id}/mode` allows `orchestrator`; unknown mode guard updated; orchestrator specialist list capped at 3 in both turn paths | Updated `apps/api/app/api/v1/routes/rooms.py` and added cap guard in both non-stream and streaming orchestrator selection paths in `sessions.py`. |
| W21-04 | Tests | DONE | Required orchestrator synthesis, mode patch, and cap scenarios covered | Added orchestrator completion tests in `tests/test_sessions_routes.py`; updated mode patch tests in `tests/test_rooms_routes.py`; adjusted one history expectation in `tests/test_standalone_sessions.py` for manager synthesis row. |

## Verification
- Full suite: `196/196` passing.
- Ruff critical (`E9,F63,F7,F82`): passing.
- Alembic head unchanged: `20260223_0018`.

## Carry-Forwards At Week 21 Close
| ID | Severity | Description |
|---|---|---|
| F58 | Low | `uploaded_files.user_id` index deferred. |
| F62 | Low | `file_read` compile-per-turn behavior accepted at current throughput. |
| F64 | Low | Worker DB URL precedence remains explicit deployment policy. |
| F70 | Medium | Staging deploy drift closes on next staging redeploy with current branch. |
