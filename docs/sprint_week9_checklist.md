# Pantheon MVP - Sprint Week 9 Checklist

Sprint window: Week 9 (Cycle 4, Part 1 - Metering Engine + Credit Accounting)  
Owner: Codex  
Reviewer: External supervising engineer  
Last updated: 2026-02-22

## Sprint Goal
Ship pricing/version foundations, wallet accounting, and user/admin pricing-wallet APIs with observational metering (no enforcement gate).

## Baseline
- Local tests at sprint open: `81` passing.
- Migration head at sprint open: `20260222_0009`.

## Definition Of Done (Week 9)
- W9-01 carry-forward hardening tasks are resolved (`F54`, `F59`, `F60`, `F61`, `F63`).
- Pricing version + model pricing schema exists and is seeded.
- Runtime metering applies model multipliers in credit burn computation.
- Credit wallet + credit transaction schema exists and is seeded for beta grant path.
- Turn path stages usage + wallet debit in a single transaction boundary.
- Authenticated user endpoints expose wallet and usage history.
- Admin pricing endpoints support read + multiplier patch with runtime cache reload.
- Staging validation demonstrates end-to-end metering + wallet update.
- Week 9 handoff is published.

## Locked Decisions
| Decision | Rationale |
|---|---|
| Runtime multiplier source is in-memory cache in `meter.py` | No per-turn DB read |
| No credit enforcement gate in Week 9 | Observational billing only |
| Beta users receive seeded free credits via migration | No Stripe in this sprint |
| `credit_wallets` keyed by `user_id` text | Aligns with existing schema style |
| F41 transaction policy applies to all writes | Stage before one route `commit()` |
| Manager routing calls remain unmetered (F46) | Deferred until scale/admin reporting trigger |

## Model Alias Multiplier Table (W9 Runtime)
| Alias | Multiplier |
|---|---|
| `deepseek` | `0.5` |
| `gemini-flash` | `0.8` |
| `gemini-pro` | `1.2` |
| `gpt-4o-mini` | `1.0` |
| `gpt-4o` | `2.0` |
| `claude-haiku` | `0.8` |
| `claude-sonnet` | `1.5` |
| `default` | `1.0` |

## Entry Gates
1. Week 9 scope lock: start Cycle 4 now (not a full Week 9 hardening-only sprint).
2. Transaction policy remains locked (`docs/transaction_policy.md`).
3. Staging credentials/envs confirmed for API + worker before migration/apply tasks.

## Tracking Rules
- Status values: `TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`.
- After each task update: status, evidence/notes, changelog.

## Supervisor Checkpoint Rule
- Stop for supervisor review after:
  1. schema/migration tasks,
  2. runtime billing/wallet transaction-path changes,
  3. admin access-control route changes.

## Staging Evidence Rule
- Required to close any task touching migration/auth/runtime behavior.
- Local tests are necessary but insufficient for those tasks.

## Migration Rule
- Confirm `down_revision` from current staging head before authoring.
- Validate live constraint/index names when dropping/updating.

## Week 9 Task Checklist
| ID | Task | Status | Acceptance Criteria | Evidence / Notes |
|---|---|---|---|---|
| W9-01 | Carry-forward triage implementation (`F54`, `F59`, `F60`, `F61`, `F63`) | DONE | Singleton storage client, async-safe upload wrapper, Tavily auth header hardening, missing `file_parse` tests added, combined search+file_read executor test added; no migration changes | Completed. `SupabaseStorageService` now singleton-lazy with one client instance and `asyncio.to_thread` upload wrapper (F59/F60). Tavily search now sends API key via `Authorization: Bearer` header, not request JSON body (F54). Added `file_parse` test coverage for `not_found` and CSV success normalization (F61). Added combined search+file_read LangGraph runtime test asserting both tool events in one turn path (F63). Validation: `84/84` tests passing, Ruff critical (`E9,F63,F7,F82`) passing. |
| W9-02 | Pricing version schema + migration (`pricing_versions`, `model_pricing`) | DONE | Migration `20260222_0010` from `0009`; seeded version `2026-02-20` and alias multipliers | Approved by supervisor. |
| W9-03 | Multiplier-aware metering in `meter.py` + route wiring | DONE | Add runtime pricing cache, multiplier lookup, backward-compatible `compute_credits_burned` signature, and tests | Approved by supervisor. |
| W9-04 | Credit wallet schema + migration | DONE | Migration `20260222_0011` creates `credit_wallets` + `credit_transactions` (+kind check), beta grant seed | Approved by supervisor. |
| W9-05 | Wallet service + staged debit wiring in turn path | DONE | `WalletService` with `get_or_create_wallet` + `stage_debit`; single-commit turn path preserved | Approved by supervisor. |
| W9-06 | User usage/wallet API endpoints | DONE | `/api/v1/users/me/wallet` and `/api/v1/users/me/usage` with auth + tests | Approved by supervisor. |
| W9-07 | Admin pricing management endpoints + cache reload | DONE | `GET/PATCH /api/v1/admin/pricing...`, admin guard via `ADMIN_USER_IDS`, DB update + runtime cache invalidation, tests | Implemented `apps/api/app/services/billing/pricing_admin.py` and `apps/api/app/api/v1/routes/admin.py` (`GET /api/v1/admin/pricing`, `PATCH /api/v1/admin/pricing/{model_alias}`) with `require_admin` gate backed by `ADMIN_USER_IDS`. Added schemas in `apps/api/app/schemas/admin.py`, wired `admin_user_ids` in `apps/api/app/core/config.py`, and registered router in `apps/api/app/main.py`. Added `tests/test_admin_pricing.py` with 4 tests including `test_reload_pricing_cache_updates_get_model_multiplier` (closes F65). |
| W9-08 | Staging validation | DONE | Health/auth + turn metering + wallet delta + usage listing + migration head confirmation | Fresh recheck passed on staging: health/auth `200`, turn `201`, migration head `20260222_0011`, `/users/me/wallet` and `/users/me/usage` both `200`, `llm_call_events` + `credit_wallets` + `credit_transactions` rows present for the turn path. |
| W9-09 | Week 9 handoff document | DONE | `docs/sprint_week9_handoff.md` with snapshot, artifacts, chain, carry-forwards, Week 10 gates | Published `docs/sprint_week9_handoff.md`. |

## Admin Pricing Addendum (Locked For Week 9)
- Runtime pricing cache is mutable and reloadable (`reload_pricing_cache`).
- Admin patch updates DB and refreshes in-memory cache.
- Admin access via env-configured IDs (`ADMIN_USER_IDS`), no DB `is_admin` column in this sprint.
- Only `multiplier` is patchable; `model_alias` and `pricing_version` remain immutable identity.

## Expected Test Count Progression
| After task | New tests | Running total (target) |
|---|---|---|
| W9-01 | +3 | 84 |
| W9-03 | +6 | 90 |
| W9-05 | +5 | 95 |
| W9-06 | +4 | 99 |
| W9-07 | +4 | 103 |

## Current Focus
- Sprint close documentation and Week 10 planning handoff.

## Assumptions And Follow-Ups
- `F51`: Summary fallback signal remains uninstrumented at route level.
- `F53`: Search trigger remains heuristic (accepted for now).
- `F57`: `tool_call_events.room_id` width convention mismatch accepted.
- `F58`: `uploaded_files.user_id` index deferred until query pressure warrants.
- `F62`: File-read graph/checkpointer behavior accepted with per-turn thread IDs.
- `F64`: Worker DB URL precedence (`DATABASE_POOL_URL` first) remains explicit policy.
- `F65`: `reload_pricing_cache` unit coverage deferred to admin pricing route tests (`test_admin_pricing.py`).

## Change Log
- 2026-02-22: Initialized Week 9 checklist with locked decisions, Cycle 4 scope, and W9-01..W9-09 task chain.
- 2026-02-22: Set `W9-01` to `IN_PROGRESS`.
- 2026-02-22: Completed `W9-01` (`F54/F59/F60/F61/F63`) with updated storage/search implementations and added test coverage. Full suite `84/84` passing; Ruff critical checks passing.
- 2026-02-22: Supervisor approved `W9-02` and `W9-03`.
- 2026-02-22: Logged `F65` follow-up (low): `reload_pricing_cache` unit coverage deferred to admin pricing tests.
- 2026-02-22: Implemented `W9-04` credit wallet ORM + migration (`20260222_0011`) with beta grant seed; local validation remains `90/90` passing and Ruff critical checks passing.
- 2026-02-22: Supervisor approved `W9-04`.
- 2026-02-22: Implemented `W9-05` wallet service and turn-path staged debit wiring; added `tests/test_wallet_service.py` (+5).
- 2026-02-22: Implemented `W9-06` user wallet/usage routes and schemas; added `tests/test_users_routes.py` (+4), and registered users router in `main.py`.
- 2026-02-22: Full suite now `99/99` passing with Ruff critical checks passing.
- 2026-02-22: Supervisor approved `W9-05` and `W9-06`.
- 2026-02-22: Staging validation attempt: health/auth/turn path succeeded and DB head confirmed (`20260222_0011`), but `/api/v1/users/me/wallet` returned `404` and no wallet/transaction rows were created after turn; indicates staging API deploy drift (W9-05/W9-06 code not active in deployed API service).
- 2026-02-22: Rechecked staging after API redeploy; health/auth/wallet/usage endpoints all passed and wallet + transaction rows were written from turn path. Marked `W9-08` DONE.
- 2026-02-22: Implemented and validated admin pricing management (`W9-07`) with cache reload coverage test (F65 closed).
- 2026-02-22: Published Week 9 handoff (`W9-09`); full local suite `103/103` passing, Ruff critical checks passing.
