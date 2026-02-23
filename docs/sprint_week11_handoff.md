# Sprint Week 11 Handoff

## Sprint Goal
Deliver Cycle 4 Part 3: configurable credit enforcement signaling (`402` when enabled), grant/debit audit attribution via `initiated_by`, and day-bucketed admin usage reporting.

## Completion Snapshot
- Tasks closed: `W11-01` through `W11-06`.
- Local test suite at close: `122/122` passing.
- Ruff critical checks (`E9,F63,F7,F82`): passing.
- Migration head at close: `20260222_0012`.
- Staging validation summary:
  - `GET /api/v1/health -> 200`
  - `GET /api/v1/auth/me -> 200`
  - `alembic_version -> 20260222_0012`
  - Enforcement ON (`CREDIT_ENFORCEMENT_ENABLED=true`): depleted-wallet turn rejected with `402` and detail `Insufficient credits. Please top up your account.`
  - Enforcement OFF (`CREDIT_ENFORCEMENT_ENABLED=false`): depleted-wallet turn accepted (`201`) with `balance_after` and `low_balance=true`
  - `GET /api/v1/users/me/transactions -> 200` with `initiated_by` in response items
  - `POST /api/v1/admin/wallets/{user_id}/grant -> 200` and `GET /api/v1/admin/wallets/{user_id} -> 200` with non-null `initiated_by` for latest grant transaction
  - `GET /api/v1/admin/usage/summary?bucket=day -> 200` with `daily` list present and non-empty

## Delivered Artifacts
- W11-01 (F67 fix + attribution schema):
  - Updated `AdminGrantRequest.amount` validation to `Field(gt=0.0, le=10_000.0)` in `apps/api/app/schemas/admin.py` (closes F67).
  - Added migration `infra/alembic/versions/20260222_0012_add_initiated_by_to_credit_transactions.py`.
  - Added `initiated_by` column to ORM model `CreditTransaction` in `apps/api/app/db/models.py`.
  - Wired `initiated_by` through `stage_grant` in `apps/api/app/services/billing/wallet.py`.
  - Grant endpoint now passes acting admin id in `apps/api/app/api/v1/routes/admin.py`.

- W11-02 (configurable enforcement gate):
  - Added `_bool_env(...)` and `credit_enforcement_enabled` in `apps/api/app/core/config.py`.
  - Added preflight turn check in `apps/api/app/api/v1/routes/sessions.py`:
    - if enforcement enabled and wallet balance `<= 0`, return `HTTP 402`.
  - Added enforcement tests in `tests/test_sessions_routes.py` for enabled and disabled modes.

- W11-03 (date-bucketed admin usage report):
  - Extended admin usage summary schema in `apps/api/app/schemas/admin.py` with:
    - `AdminUsageDailyBucket`
    - `AdminUsageSummaryRead.daily`
  - Extended `GET /api/v1/admin/usage/summary` in `apps/api/app/api/v1/routes/admin.py` with optional `bucket=day` and grouped daily aggregates.
  - Added tests in `tests/test_admin_pricing.py`:
    - `test_usage_summary_daily_bucket`
    - `test_usage_summary_no_bucket_daily_empty`

- W11-04 (surface `initiated_by` + F68 cleanup):
  - Added `initiated_by` to user transaction schema in `apps/api/app/schemas/users.py`.
  - Included `initiated_by` in `/users/me/transactions` mapping in `apps/api/app/api/v1/routes/users.py`.
  - Added deterministic env/cache cleanup in enforcement tests via `self.addCleanup(...)` in `tests/test_sessions_routes.py` (closes F68).
  - Added assertion coverage in `tests/test_users_routes.py` for `initiated_by`.

- W11-05 (staging validation):
  - Validated both enforcement modes on staging and verified new API response contracts.
  - Confirmed admin grant attribution persistence and daily usage bucket payload.

- W11-06 (handoff):
  - Published this handoff with full evidence, chain, and Week 12 entry gates.

## Runtime Capability At Close
Compared with Week 10 close, the service now supports:
- runtime-configurable credit enforcement behavior (`402` vs allow) without code changes
- explicit admin attribution for grant transactions (`initiated_by`)
- day-bucketed admin usage reporting from `llm_call_events`
- consistent transaction history payloads for user and admin surfaces with attribution visibility

## Migration Chain At Close
`20260221_0001 -> 20260221_0002 -> 20260221_0003 -> 20260221_0004 -> 20260221_0005 -> 20260222_0006 -> 20260222_0007 -> 20260222_0008 -> 20260222_0009 -> 20260222_0010 -> 20260222_0011 -> 20260222_0012`

## Carry-Forward Follow-Ups (Week 12+)
| ID | Severity | Description |
|---|---|---|
| F51 | Low | `SummaryGenerationResult.used_fallback` still not emitted into route-level observability. |
| F53 | Low | Search trigger remains heuristic (`search:` / `search for`) rather than model-driven tool dispatch. |
| F57 | Low | `tool_call_events.room_id` width differs from broader ID-width convention. |
| F58 | Low | `uploaded_files.user_id` index remains deferred until query pressure warrants. |
| F62 | Low | `file_read` graph path compiles per turn when DB closure is needed; accepted for current throughput. |
| F64 | Low | Worker DB URL precedence (`DATABASE_POOL_URL` first) should remain explicit deployment policy. |

## Week 12 Entry Gates
1. Scope lock enforcement policy for production rollout:
   - keep default non-blocking in shared environments
   - define rollout procedure and rollback for enabling enforcement per environment.
2. Decide whether `initiated_by` should also be surfaced in additional admin exports/report views.
3. Confirm whether admin usage reporting needs weekly/monthly buckets beyond `day`.
4. Keep F41 transaction policy locked for any new billing write paths.
