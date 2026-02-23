# Pantheon MVP - Sprint Week 19 Checklist

Sprint window: Week 19 (Cycle 6 Part 3 - Round Table Parity + Mode Management)  
Owner: Codex  
Reviewer: External supervising engineer  
Last updated: 2026-02-23

## Sprint Goal
Close Cycle 6 by validating non-stream roundtable parity, adding room mode management endpoint, and finalizing roundtable persistence/usage commit guarantees under tests.

## Baseline
- Local tests at sprint open: `175` passing.
- Migration head at sprint open: `20260223_0018`.

## Definition of Done
- Non-stream `create_turn` roundtable path is audited/aligned with streaming behavior.
- `PATCH /rooms/{room_id}/mode` exists with orchestrator guard.
- 5 mode endpoint tests pass.
- 5 roundtable parity tests pass.
- Week 19 handoff is published.

## Week 19 Task Checklist
| ID | Task | Status | Acceptance Criteria | Evidence / Notes |
|---|---|---|---|---|
| W19-01 | Audit and align non-stream roundtable path | DONE | Verify 7 parity points (shared output propagation, per-agent persistence, per-agent usage, single commit) | Audited `apps/api/app/api/v1/routes/sessions.py`; all 7 points already present. No parity code change required. |
| W19-02 | Room mode change endpoint | DONE | `PATCH /rooms/{room_id}/mode` supports `manual`/`roundtable`; rejects `orchestrator` and unknown modes with 422; owner-only | Implemented in `apps/api/app/api/v1/routes/rooms.py`; schema added in `apps/api/app/schemas/rooms.py`. |
| W19-03 | Tests (mode + roundtable parity) | DONE | 10 tests: 5 mode endpoint + 5 roundtable non-streaming parity tests | Added mode tests in `tests/test_rooms_routes.py`; added roundtable parity tests in `tests/test_sessions_routes.py`. |
| W19-04 | Cycle 6 close-out docs | DONE | Publish Week 19 checklist/handoff; update Gate 3 status in enforcement criteria doc | Published `docs/sprint_week19_checklist.md`, `docs/sprint_week19_handoff.md`; updated `docs/enforcement_production_criteria.md` Gate 3 to PASS. |

## Verification
- Full suite: `185/185` passing.
- Ruff critical (`E9,F63,F7,F82`): passing.
- Alembic head unchanged: `20260223_0018`.

## Carry-Forwards At Week 19 Close
| ID | Severity | Description |
|---|---|---|
| F58 | Low | `uploaded_files.user_id` index deferred. |
| F62 | Low | `file_read` compile-per-turn behavior accepted at current throughput. |
| F64 | Low | Worker DB URL precedence remains explicit deployment policy. |
| F70 | Medium | Staging deploy drift persists until staging is redeployed with Weeks 14–19 code. |

