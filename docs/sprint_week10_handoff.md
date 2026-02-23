# Sprint Week 10 Handoff

## Sprint Goal
Deliver Cycle 4 Part 2 warn-only billing enforcement signals and admin/user reporting controls without introducing hard balance-blocking on turns.

## Completion Snapshot
- Tasks completed: `W10-01` through `W10-06`.
- Local test suite: `117/117` passing.
- Ruff critical checks (`E9,F63,F7,F82`): passing.
- Migration head at close: `20260222_0011` (no new schema migrations in Week 10).
- Staging validation summary:
  - `GET /api/v1/health -> 200`
  - `POST /api/v1/sessions/{session_id}/turns -> 201` with `balance_after` and `low_balance` in response
  - `GET /api/v1/users/me/wallet -> 200`
  - `GET /api/v1/users/me/transactions -> 200` with latest debit present
  - `POST /api/v1/admin/wallets/{user_id}/grant -> 200`
  - `GET /api/v1/admin/wallets/{user_id} -> 200` with updated balance and recent transactions
  - `GET /api/v1/admin/usage/summary -> 200`

## Delivered Artifacts
- W10-01 (shared decimal utility + precision contract):
  - Added `apps/api/app/utils/decimal_format.py` and `apps/api/app/utils/__init__.py`.
  - Replaced duplicated formatting logic in:
    - `apps/api/app/api/v1/routes/users.py`
    - `apps/api/app/api/v1/routes/admin.py`
  - Added precision contract comment in `apps/api/app/services/billing/wallet.py`.
  - Added tests: `tests/test_decimal_format.py`.

- W10-02 (low-balance warn signal in turn response):
  - Added `low_balance_threshold` setting in `apps/api/app/core/config.py` (`LOW_BALANCE_THRESHOLD`, default `5.0`).
  - Extended `TurnRead` response schema in `apps/api/app/schemas/chat.py`:
    - `balance_after`
    - `low_balance`
  - Updated turn execution response wiring in `apps/api/app/api/v1/routes/sessions.py` to emit warn-only balance signal.
  - Added tests in `tests/test_sessions_routes.py`:
    - `test_turn_response_includes_balance_after`
    - `test_turn_response_low_balance_flag`

- W10-03 (admin usage summary endpoint):
  - Added admin summary schema types in `apps/api/app/schemas/admin.py`:
    - `AdminUsageBreakdownItem`
    - `AdminUsageSummaryRead`
  - Added endpoint `GET /api/v1/admin/usage/summary` in `apps/api/app/api/v1/routes/admin.py` with optional filters:
    - `user_id`
    - `model_alias`
    - `from_date`
    - `to_date`
  - Added summary aggregation tests in `tests/test_admin_pricing.py`:
    - empty
    - filtered by user
    - filtered by model

- W10-04 (admin wallet management):
  - Extended wallet service in `apps/api/app/services/billing/wallet.py` with `stage_grant`.
  - Added admin wallet schema types in `apps/api/app/schemas/admin.py`:
    - `AdminTransactionRead`
    - `AdminWalletRead`
    - `AdminGrantRequest`
    - `AdminGrantResponse`
  - Added admin wallet endpoints in `apps/api/app/api/v1/routes/admin.py`:
    - `GET /api/v1/admin/wallets/{user_id}`
    - `POST /api/v1/admin/wallets/{user_id}/grant`
  - Added tests: `tests/test_admin_wallets.py` (4 tests).

- W10-05 (user transaction history):
  - Added user transaction schema types in `apps/api/app/schemas/users.py`:
    - `TransactionRead`
    - `TransactionListRead`
  - Added endpoint `GET /api/v1/users/me/transactions` in `apps/api/app/api/v1/routes/users.py`.
  - Added tests in `tests/test_users_routes.py`:
    - `test_get_transactions_empty`
    - `test_get_transactions_returns_own_only`
    - `test_get_transactions_pagination`

- W10-06 (staging validation + closure):
  - Verified full warn-only enforcement/reporting flow on staging including admin grant and usage summary endpoints.
  - Confirmed admin gating depends on `ADMIN_USER_IDS` in deployed config.

## Runtime Capability At Close
Compared with Week 9 close, the service now supports:
- warn-only balance signals on turn responses (`balance_after`, `low_balance`) without blocking turn completion
- user-facing transaction history pagination
- admin wallet inspection and grant operations
- admin usage summary aggregation from `llm_call_events`
- shared decimal string formatting utility across route modules

## Precision Contract (Locked)
- `credit_transactions.amount` (`Numeric(18,8)`): ledger truth, full precision.
- `llm_call_events.credits_burned` (`Numeric(20,4)`): usage-event display/report precision.
- These are intentionally different and remain unchanged.

## Carry-Forward Follow-Ups (Week 11+)
| ID | Severity | Description |
|---|---|---|
| F51 | Low | `SummaryGenerationResult.used_fallback` not emitted into route observability yet. |
| F53 | Low | Search trigger remains heuristic rather than model-driven/function-calling dispatch. |
| F57 | Low | `tool_call_events.room_id` width differs from broader ID-width convention. |
| F58 | Low | `uploaded_files.user_id` index still deferred until query pressure warrants. |
| F62 | Low | `file_read` graph path compiles per turn when DB closure is needed. |
| F64 | Low | Worker DB URL precedence (`DATABASE_POOL_URL` first) should remain explicit policy. |
| F67 | Low | `AdminGrantRequest.amount` currently uses `Field(le=10_000.0)` without `gt=0.0`; route-level `400` check compensates, but schema-level validation should also enforce positive amounts. |

## Week 11 Entry Gates
1. Scope lock Cycle 4 next phase: keep warn-only or begin configurable enforcement gates.
2. Decide admin cost report expansion (time buckets/export) beyond current summary endpoint.
3. Confirm if grant/debit audit needs actor attribution fields (admin user id) in schema.
4. Maintain F41 transaction policy for all new billing write paths.
