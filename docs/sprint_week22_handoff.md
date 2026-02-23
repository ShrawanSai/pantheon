# Sprint Week 22 Handoff

## Sprint Goal
Deliver the admin analytics endpoints required by the master plan and run the consolidated staging validation attempt to close F70 when staging parity is available.

## Completion Snapshot
- Tasks completed: `W22-01` through `W22-05`.
- Local tests at close: `203/203` passing.
- Ruff critical checks (`E9,F63,F7,F82`): passing.
- Migration head at close (local): `20260223_0018`.

## Delivered Artifacts
- W22-01 (admin usage analytics):
  - Updated `apps/api/app/api/v1/routes/admin.py` with:
    - `GET /api/v1/admin/analytics/usage`
  - Updated `apps/api/app/schemas/admin.py` with:
    - `AdminUsageAnalyticsRowRead`
    - `AdminUsageAnalyticsRead`
  - Behavior:
    - required `start_date`, `end_date`
    - paginated grouped rows by `(user_id, model_alias)`
    - aggregated input/output/credits/event_count
    - stable credit formatting via `format_decimal(...)`

- W22-02 (admin active-users analytics):
  - Updated `apps/api/app/api/v1/routes/admin.py` with:
    - `GET /api/v1/admin/analytics/active-users`
  - Updated `apps/api/app/schemas/admin.py` with:
    - `AdminActiveUsersRead`
  - Behavior:
    - `window`: `day|week|month`
    - optional `as_of`
    - `active_users`: distinct `started_by_user_id` in window
    - `new_users`: first-session subquery constrained to same window

- W22-03 (staging validation / F70 closure attempt):
  - Executed staging validation script (`tmp_w16_staging_validate.py`) after W22 code completion.
  - Observed blocker evidence:
    - Staging DB head: `20260223_0013`
    - `POST /api/v1/agents` -> `404`
    - `GET /api/v1/agents` -> `404`
    - `GET /api/v1/health` -> `200`
    - `GET /api/v1/admin/settings` -> `200`
  - Conclusion: staging not redeployed with Week 14+ routes/migrations; F70 remains open.

- W22-04 (tests):
  - Added `tests/test_admin_analytics.py` with 7 tests:
    - `test_usage_analytics_aggregates_by_user_model`
    - `test_usage_analytics_filters_by_date_range`
    - `test_usage_analytics_non_admin_rejected`
    - `test_active_users_day_window`
    - `test_active_users_week_window`
    - `test_active_users_new_users_count`
    - `test_active_users_non_admin_rejected`

- W22-05 (docs):
  - Published `docs/sprint_week22_checklist.md`
  - Published `docs/sprint_week22_handoff.md`

## Cycle 7 Summary (Weeks 20-22)
- W20: Per-user rate limiting for turn endpoints (`/turns`, `/turns/stream`) with Redis-backed sliding windows.
- W21: Orchestrator completion with manager synthesis in both streaming/non-streaming flows, mode patch unlock, and invocation cap guard.
- W22: Admin analytics endpoints for usage aggregation and active-user metrics, plus staging closure attempt for deploy drift.

## Runtime Capability At Close
Compared with Week 21 close:
- Admins can query aggregate usage by user/model over explicit date windows.
- Admins can query active/new user counts over day/week/month windows.
- Analytics endpoints are admin-guarded and fully covered by route-level tests.

## Migration Chain At Close
`20260221_0001 -> 20260221_0002 -> 20260221_0003 -> 20260221_0004 -> 20260221_0005 -> 20260222_0006 -> 20260222_0007 -> 20260222_0008 -> 20260222_0009 -> 20260222_0010 -> 20260222_0011 -> 20260222_0012 -> 20260223_0013 -> 20260223_0014 -> 20260223_0015 -> 20260223_0016 -> 20260223_0017 -> 20260223_0018`

## Carry-Forward Follow-Ups
| ID | Severity | Description |
|---|---|---|
| F58 | Low | `uploaded_files.user_id` index deferred. |
| F62 | Low | `file_read` compile-per-turn behavior accepted at current throughput. |
| F64 | Low | Worker DB URL precedence remains explicit deployment policy. |
| F70 | Medium | Staging deploy drift persists (`0013` deployed on staging; Week 14+ routes unavailable). |

## Week 23 Entry Gates
1. Cycle 8 scope requires product-owner lock (candidates: multi-round orchestrator depth loop, long-term memory/pgvector, frontend API consistency, observability expansion).
2. Staging must be redeployed with Week 14+ branch before attempting to close F70.
3. `TBD_ACTIVE_USERS` and `TBD_EVENTS_PER_DAY` in `docs/enforcement_production_criteria.md` remain product-owner inputs; do not fabricate.
4. Keep F41 transaction policy locked for all future write paths.
