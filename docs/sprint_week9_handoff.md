# Sprint Week 9 Handoff

## Sprint Goal
Deliver Cycle 4 Part 1 billing foundations: multiplier-aware metering, credit wallet accounting, user usage/wallet APIs, and admin pricing controls with runtime cache sync.

## Completion Snapshot
- Tasks closed: `W9-01` through `W9-09`.
- Test suite at close: `103/103` passing.
- Ruff critical checks (`E9,F63,F7,F82`): passing.
- Migration head at close: `20260222_0011`.
- Staging validation highlights:
  - `GET /api/v1/health -> 200`
  - `GET /api/v1/auth/me -> 200`
  - `POST /api/v1/sessions/{session_id}/turns -> 201`
  - `GET /api/v1/users/me/wallet -> 200`
  - `GET /api/v1/users/me/usage -> 200`
  - DB evidence: `llm_call_events`, `credit_wallets`, and `credit_transactions` rows present for the validated turn path.

## Delivered Artifacts
- W9-01 (carry-forward hardening):
  - `apps/api/app/services/storage/supabase_storage.py` singletonized and upload moved to `asyncio.to_thread` (`F59`, `F60`).
  - `apps/api/app/services/tools/search_tool.py` switched Tavily auth to `Authorization: Bearer` header (`F54`).
  - Added test coverage in `tests/test_file_parse_job.py` (`not_found`, CSV success) (`F61`).
  - Added combined search+file_read runtime test in `tests/test_langgraph_mode_executor.py` (`F63`).

- W9-02 (pricing schema):
  - Added `PricingVersion` and `ModelPricing` ORM models in `apps/api/app/db/models.py`.
  - Added migration `infra/alembic/versions/20260222_0010_create_pricing_tables.py` with seed data for version `2026-02-20` and model multipliers.

- W9-03 (multiplier-aware metering):
  - Updated runtime pricing cache + reload path in `apps/api/app/services/usage/meter.py`.
  - Wired multiplier usage into turn metering in `apps/api/app/api/v1/routes/sessions.py`.
  - Added meter tests in `tests/test_meter.py`.

- W9-04 (credit schema):
  - Added `CreditWallet` and `CreditTransaction` ORM models in `apps/api/app/db/models.py`.
  - Added migration `infra/alembic/versions/20260222_0011_create_credit_tables.py` including beta grant seed.

- W9-05 (wallet service + turn wiring):
  - Implemented `apps/api/app/services/billing/wallet.py` with `get_or_create_wallet` + `stage_debit`.
  - Wired staged debit into turn write path in `apps/api/app/api/v1/routes/sessions.py` before single commit.
  - Added tests in `tests/test_wallet_service.py`.

- W9-06 (user wallet/usage APIs):
  - Added `apps/api/app/api/v1/routes/users.py` endpoints:
    - `GET /api/v1/users/me/wallet`
    - `GET /api/v1/users/me/usage`
  - Added response schemas in `apps/api/app/schemas/users.py`.
  - Added tests in `tests/test_users_routes.py`.

- W9-07 (admin pricing management + cache reload):
  - Added `apps/api/app/services/billing/pricing_admin.py`.
  - Added admin routes in `apps/api/app/api/v1/routes/admin.py`:
    - `GET /api/v1/admin/pricing`
    - `PATCH /api/v1/admin/pricing/{model_alias}`
  - Added admin schemas in `apps/api/app/schemas/admin.py`.
  - Added `ADMIN_USER_IDS` config support in `apps/api/app/core/config.py`.
  - Registered admin router in `apps/api/app/main.py`.
  - Added tests in `tests/test_admin_pricing.py` (includes `reload_pricing_cache` coverage; closes `F65`).

- W9-08 (staging validation):
  - Confirmed end-to-end metering + wallet flow on staging with migration head `20260222_0011`.
  - Verified expected numeric behavior:
    - `llm_call_events.credits_burned` rounded to `Numeric(20,4)`
    - `credit_transactions.amount` preserved at `Numeric(18,8)` precision.

## Runtime Capability At Close
Compared with Week 8 close, the system now supports:
- model-multiplier-aware credit burn computation at turn time
- persisted pricing catalog/version schema
- per-user wallet balance mutation and debit transaction recording in the same transaction as turn usage staging
- authenticated wallet/usage read APIs for end users
- admin-controlled multiplier updates that persist in DB and refresh runtime pricing cache without restart

## Migration Chain At Close
`20260221_0001 -> 20260221_0002 -> 20260221_0003 -> 20260221_0004 -> 20260221_0005 -> 20260222_0006 -> 20260222_0007 -> 20260222_0008 -> 20260222_0009 -> 20260222_0010 -> 20260222_0011`

## Carry-Forward Follow-Ups (Week 10+)
| ID | Severity | Description |
|---|---|---|
| F51 | Low | `SummaryGenerationResult.used_fallback` still not emitted into route-level observability. |
| F53 | Low | Search trigger remains heuristic (`search:` / `search for`) rather than model-driven tool dispatch. |
| F57 | Low | `tool_call_events.room_id` width differs from broader ID-width convention. |
| F58 | Low | `uploaded_files.user_id` index remains deferred until query pressure warrants. |
| F62 | Low | `file_read` graph path compiles per turn when DB closure is needed; acceptable for current throughput. |
| F64 | Low | Worker DB URL precedence (`DATABASE_POOL_URL` first) should remain explicit in runbooks/policy. |
| F66 | Low | `_decimal_to_string` is duplicated in `apps/api/app/api/v1/routes/users.py` and `apps/api/app/api/v1/routes/admin.py`; consolidate if a third callsite appears. |

## Week 10 Entry Gates
1. Confirm Cycle 4 Part 2 scope lock: enforcement policy (warn-only vs hard gate) and admin cost reporting scope.
2. Decide precision policy for surfaced credits (`4dp` event summary vs `8dp` ledger accuracy) and document API contract.
3. Confirm staging env parity for API + worker + migrations before new billing/administration changes.
4. Keep F41 transaction policy locked for all new billing write paths.
