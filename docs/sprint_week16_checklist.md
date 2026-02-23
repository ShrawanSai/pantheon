# Pantheon MVP - Sprint Week 16 Checklist

Sprint window: Week 16 (Cycle 5 Close-Out)  
Owner: Codex  
Reviewer: External supervising engineer  
Last updated: 2026-02-23

## Sprint Goal
Add formal `source_agent_key` attribution on messages, complete semantic attribution cleanup in context assembly, run consolidated staging validation, and close Cycle 5 with handoff.

## Baseline
- Local tests at sprint open: `160` passing.
- Migration head at sprint open: `20260223_0017`.

## Definition of Done
- `messages.source_agent_key` exists with backfill from `agent_key`.
- Message write paths persist `source_agent_key` per semantic contract.
- Context attribution reads `source_agent_key` (not scratchpad `agent_key`) for other-agent labeling.
- Consolidated W14/W15/W16 staging legs executed and recorded.
- Week 16 handoff published with Cycle 5 summary and Week 17 gates.

## Block Structure
- Block 1: `W16-01`, `W16-02`
- Block 2: `W16-03`, `W16-04`

## Week 16 Task Checklist
| ID | Task | Status | Acceptance Criteria | Evidence / Notes |
|---|---|---|---|---|
| W16-01 | `source_agent_key` migration + ORM + write path | DONE | Migration `20260223_0018_messages_source_agent_key.py`; Message ORM field + semantic comment; all write paths set value correctly | Implemented in `infra/alembic/versions/20260223_0018_messages_source_agent_key.py`, `apps/api/app/db/models.py`, `apps/api/app/api/v1/routes/sessions.py`. Added 3 tests in `tests/test_sessions_routes.py`. |
| W16-02 | Context assembly attribution uses `source_agent_key` | DONE | Other-agent context labeling key switched to `source_agent_key` while preserving behavior | Implemented in `_build_history_messages_for_agent` in `apps/api/app/api/v1/routes/sessions.py`. |
| W16-03 | Consolidated staging validation + F70 status | BLOCKED | Execute all W14/W15/W16 legs post-redeploy; confirm alembic head `20260223_0018` | Executed `tmp_w16_staging_validate.py`. Staging returns `404` for `/api/v1/agents*`, and DB alembic head is `20260223_0013`. F70 remains open and carried. |
| W16-04 | Cycle 5 close-out handoff | DONE | Publish `docs/sprint_week16_handoff.md` with Cycle 5 summary, close-state, carry-forwards, and Week 17 gates | Published handoff with full local evidence and staging blocker details. |

## Block 1 Verification
- Tests: `163/163` passing (`.venv\\Scripts\\python.exe -m pytest -q`)
- Ruff critical (`E9,F63,F7,F82`): passing
- Alembic heads (local): `20260223_0018 (head)`

## Carry-Forwards At Week 16 Close
| ID | Severity | Description |
|---|---|---|
| F58 | Low | `uploaded_files.user_id` index deferred. |
| F62 | Low | `file_read` graph compile-per-turn behavior accepted at current throughput. |
| F64 | Low | Worker DB URL precedence remains explicit deployment policy. |
| F70 | Medium | Staging deploy drift: Week 14+ routes and migrations not active on deployed staging instance. |

