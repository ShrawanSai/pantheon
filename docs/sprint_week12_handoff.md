# Sprint Week 12 Handoff

## Sprint Goal
Close out Cycle 4 billing controls by adding runtime enforcement toggles, extending admin usage bucketing, surfacing summary fallback metadata in turn responses, and shipping enforcement rollout operations guidance.

## Completion Snapshot
- Tasks targeted: `W12-01` through `W12-06`.
- Local test suite at close: `129/129` passing.
- Ruff critical checks (`E9,F63,F7,F82`): passing.
- Migration head at close: `20260222_0012` (no new migrations in Week 12).
- Staging validation status:
  - Core health/auth path: pass (`200/200`).
  - New admin settings toggle endpoints: blocked (`404 Not Found` from staging API deploy drift).
  - Week/month bucket behavior: endpoint `200`, but response remained legacy (`daily: []`) for week/month on staging.
  - `summary_used_fallback` response field: missing on staging response (deploy drift).

## Delivered Artifacts
- W12-01 (runtime enforcement toggle):
  - Added in-memory override service: `apps/api/app/services/billing/enforcement.py`.
  - Updated turn enforcement gate to use override-aware effective state in `apps/api/app/api/v1/routes/sessions.py`.
  - Added admin endpoints in `apps/api/app/api/v1/routes/admin.py`:
    - `GET /api/v1/admin/settings`
    - `PATCH /api/v1/admin/settings/enforcement`
    - `DELETE /api/v1/admin/settings/enforcement`
  - Added schemas in `apps/api/app/schemas/admin.py`:
    - `AdminEnforcementUpdate`
    - `AdminEnforcementRead`
    - `AdminSettingsRead`
  - Added tests: `tests/test_admin_settings.py` (4 tests).

- W12-02 (week/month usage buckets):
  - Extended `GET /api/v1/admin/usage/summary` bucket handling in `apps/api/app/api/v1/routes/admin.py` for `day`, `week`, and `month`.
  - Implemented dialect-safe week/month bucketing path:
    - SQLite test path uses date expressions
    - Postgres runtime path uses `date_trunc`
  - Reused daily bucket schema shape via `AdminUsageBucket` in `apps/api/app/schemas/admin.py`.
  - Added tests in `tests/test_admin_pricing.py`:
    - `test_usage_summary_monthly_bucket`
    - `test_usage_summary_unknown_bucket_daily_empty`

- W12-03 (F51 closure on turn response):
  - Added `summary_used_fallback: bool = False` to `TurnRead` in `apps/api/app/schemas/chat.py`.
  - Wired summary generator fallback signal into turn response in `apps/api/app/api/v1/routes/sessions.py`.
  - Added test in `tests/test_sessions_routes.py`:
    - `test_turn_response_summary_fallback_is_false_when_no_summary`

- W12-04 (enforcement rollout runbook):
  - Published `docs/enforcement_rollout.md` with enable/verify/rollback procedures, behavior matrix, and admin endpoint quick reference.

- W12-05 (staging validation):
  - Executed full staged leg sequence and captured per-leg status/evidence.
  - Logged deploy-drift blocker where staging API did not yet expose new Week 12 admin settings/toggle surfaces.

- W12-06 (handoff):
  - Published this handoff with completion status, evidence, and Week 13 gates.

## Runtime Capability At Close
Compared with Week 11 close, the codebase now supports:
- runtime enforcement toggle changes without redeploy (override layer)
- effective settings introspection endpoint for admins
- admin usage summary week/month buckets (same endpoint contract)
- turn-level summary fallback metadata (`summary_used_fallback`) in response contracts
- operational runbook for controlled enforcement rollout and rollback

## Migration Chain At Close
`20260221_0001 -> 20260221_0002 -> 20260221_0003 -> 20260221_0004 -> 20260221_0005 -> 20260222_0006 -> 20260222_0007 -> 20260222_0008 -> 20260222_0009 -> 20260222_0010 -> 20260222_0011 -> 20260222_0012`

## W12-05 Staging Evidence (Per Leg)
1. `GET /api/v1/health` -> `200`.
2. `GET /api/v1/auth/me` -> `200`.
3. `GET /api/v1/admin/settings` -> `404` (blocker: endpoint not active on staging deploy).
4. `PATCH /api/v1/admin/settings/enforcement {"enabled": true}` -> `404` (same blocker).
5. `GET /api/v1/admin/settings` (post-patch verify) -> `404` (same blocker).
6. Turn with depleted wallet under intended ON path -> returned `201` (could not validate `402` due missing toggle endpoint/deploy drift).
7. `DELETE /api/v1/admin/settings/enforcement` -> `404` (same blocker).
8. Same turn after clear override -> `201` with `balance_after` and `low_balance=true`.
9. `GET /api/v1/admin/usage/summary?bucket=week` -> `200`, `daily=[]`.
10. `GET /api/v1/admin/usage/summary?bucket=month` -> `200`, `daily=[]`.
11. `GET /api/v1/admin/usage/summary?bucket=day` -> `200`, `daily` non-empty.
12. Turn response `summary_used_fallback` field -> missing on staging response (deploy drift).

## Carry-Forward Follow-Ups (Week 13+)
| ID | Severity | Description |
|---|---|---|
| F53 | Low | Search trigger remains heuristic (`search:` / `search for`) rather than model-driven tool dispatch. |
| F57 | Low | `tool_call_events.room_id` width differs from broader ID-width convention. |
| F58 | Low | `uploaded_files.user_id` index remains deferred until query pressure warrants. |
| F62 | Low | `file_read` graph path compiles per turn when DB closure is needed; accepted for current throughput. |
| F64 | Low | Worker DB URL precedence (`DATABASE_POOL_URL` first) should remain explicit deployment policy. |
| F69 | Medium | Staging API deploy drift: Week 12 endpoints/fields not yet active (`/admin/settings*`, `summary_used_fallback`, week/month bucket behavior), blocking full runtime verification until redeploy. |

## Week 13 Entry Gates
1. Decide if enforcement should move toward default-on for production and define objective trigger criteria.
2. Decide whether admin usage reporting needs CSV/export beyond JSON summary.
3. Decide whether `initiated_by` attribution should expand beyond grants (e.g., selected debit/admin override flows).
4. Keep F41 transaction policy locked for any new billing write paths.
