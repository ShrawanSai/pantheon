# Pantheon MVP - Sprint Week 22 Checklist

Sprint window: Week 22 (Cycle 7 Part 3 - Admin Analytics + Staging Validation)  
Owner: Codex  
Reviewer: External supervising engineer  
Last updated: 2026-02-23

## Sprint Goal
Deliver admin analytics endpoints required by the master plan and run the consolidated staging validation attempt to close F70 when redeploy parity is available.

## Baseline
- Local tests at sprint open: `196` passing.
- Migration head at sprint open: `20260223_0018` (local).

## Definition of Done
- `/admin/analytics/usage` endpoint delivered with date-window grouped aggregation.
- `/admin/analytics/active-users` endpoint delivered for day/week/month windows.
- 7 analytics tests pass (including admin auth guard coverage).
- Staging validation attempt executed and F70 status explicitly recorded (closed or carried with blocker evidence).
- Week 22 handoff is published.

## Week 22 Task Checklist
| ID | Task | Status | Acceptance Criteria | Evidence / Notes |
|---|---|---|---|---|
| W22-01 | Admin usage analytics endpoint | DONE | `GET /admin/analytics/usage` with required params + grouped aggregates by `(user_id, model_alias)` | Implemented in `apps/api/app/api/v1/routes/admin.py`; schemas added in `apps/api/app/schemas/admin.py` (`AdminUsageAnalyticsRead`, row schema). Uses inclusive date-window bounds and paginated grouped result set. |
| W22-02 | Admin active-users analytics endpoint | DONE | `GET /admin/analytics/active-users` with `window` and `as_of` returning active/new users | Implemented in `apps/api/app/api/v1/routes/admin.py`; schema added in `apps/api/app/schemas/admin.py` (`AdminActiveUsersRead`). Uses distinct-session active user count and first-seen subquery for `new_users`. |
| W22-03 | Staging validation (F70 closure attempt) | BLOCKED (carry) | Confirm staging on head `20260223_0018` and `/agents` endpoints available | Executed `tmp_w16_staging_validate.py` against staging. Evidence: `alembic head=20260223_0013`, `POST /api/v1/agents -> 404`, `GET /api/v1/agents -> 404`. F70 remains open (deploy drift). |
| W22-04 | Analytics tests | DONE | 7 required tests pass | Added `tests/test_admin_analytics.py` with all 7 required tests: usage aggregation/date filter/non-admin and active-users day/week/new-users/non-admin. |
| W22-05 | Cycle 7 close-out docs | DONE | Publish Week 22 checklist + handoff with F70 status | Published `docs/sprint_week22_checklist.md` and `docs/sprint_week22_handoff.md` with blocker evidence and Week 23 gates. |

## Verification
- New Week 22 tests: `7/7` passing (`tests/test_admin_analytics.py`).
- Full test suite: `203/203` passing.
- Ruff critical (`E9,F63,F7,F82`): passing.
- Local migration head unchanged: `20260223_0018`.

## Carry-Forwards At Week 22 Close
| ID | Severity | Description |
|---|---|---|
| F58 | Low | `uploaded_files.user_id` index deferred. |
| F62 | Low | `file_read` compile-per-turn behavior accepted at current throughput. |
| F64 | Low | Worker DB URL precedence remains explicit deployment policy. |
| F70 | Medium | Staging deploy drift persists (`0013` on staging, `/agents` still 404). |
