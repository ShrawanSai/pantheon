# Pantheon MVP - Sprint Week 11 Checklist

Sprint window: Week 11 (Cycle 4, Part 3 - Enforcement Gate + Audit Attribution)  
Owner: Codex  
Reviewer: External supervising engineer  
Last updated: 2026-02-23

## Sprint Goal
Ship configurable credit enforcement (`402` when enabled and depleted), add grant attribution (`initiated_by`), and extend admin reporting with optional daily bucketing.

## Baseline
- Local tests at sprint open: `117` passing.
- Migration head at sprint open: `20260222_0011`.

## Locked Decisions
| Decision | Rationale |
|---|---|
| Enforcement gate is configurable (`CREDIT_ENFORCEMENT_ENABLED`, default `false`) | Existing environments remain non-blocking until explicitly enabled |
| Reject with `402 Payment Required` only when enabled and wallet balance `<= 0` | Correct HTTP semantic for payment insufficiency |
| Add nullable `initiated_by` to `credit_transactions` | Admin grants are attributable without breaking existing debit flow |
| `initiated_by` stays nullable with no FK | Avoids disruptive attribution coupling during rollout |
| Schema-level grant validation must require positive amount | Closes F67 at validation boundary |
| Admin usage summary gains optional day buckets (`bucket=day`) | Adds trend visibility without separate endpoint |

## Tracking Rules
- Status values: `TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`.
- After each task update: status, evidence/notes, changelog.

## Supervisor Checkpoint Rule
- Stop for supervisor review after each 3-task block:
  1. W11-01/W11-02/W11-03
  2. W11-04/W11-05/W11-06

## Staging Evidence Rule
- Required to close tasks touching runtime enforcement behavior, auth-protected admin/user surfaces, or deployment-sensitive schema rollout.

## Week 11 Task Checklist
| ID | Task | Status | Acceptance Criteria | Evidence / Notes |
|---|---|---|---|---|
| W11-01 | F67 fix + initiated_by schema attribution | DONE | `AdminGrantRequest.amount` uses `Field(gt=0.0, le=10_000.0)`; migration `0012` adds nullable `initiated_by`; wallet/admin wiring persists field | Implemented in `apps/api/app/schemas/admin.py`, `infra/alembic/versions/20260222_0012_add_initiated_by_to_credit_transactions.py`, `apps/api/app/db/models.py`, `apps/api/app/services/billing/wallet.py`, and `apps/api/app/api/v1/routes/admin.py`. |
| W11-02 | Configurable enforcement gate | DONE | Add `credit_enforcement_enabled` config bool; reject turn with `402` when enabled and wallet `<= 0`; tests cover enabled/disabled | Implemented in `apps/api/app/core/config.py` and `apps/api/app/api/v1/routes/sessions.py`. Added tests in `tests/test_sessions_routes.py` for both enforcement states. |
| W11-03 | Admin usage summary day bucket | DONE | `GET /api/v1/admin/usage/summary?bucket=day` returns daily aggregate with shared filters; no-bucket callers unchanged | Implemented in `apps/api/app/api/v1/routes/admin.py` + schema updates in `apps/api/app/schemas/admin.py` and tests in `tests/test_admin_pricing.py`. |
| W11-04 | Surface `initiated_by` in user transactions + F68 cleanup | DONE | `/users/me/transactions` exposes `initiated_by`; enforcement tests restore env/cache deterministically | Implemented in `apps/api/app/schemas/users.py`, `apps/api/app/api/v1/routes/users.py`, and `tests/test_users_routes.py`; enforcement test cleanup in `tests/test_sessions_routes.py`. |
| W11-05 | Staging validation | DONE | Health/auth pass; migration head `0012`; enforcement on/off confirmed; admin grant attribution confirmed; user transactions include `initiated_by`; usage summary `daily` populated | Final staging evidence captured. Enforcement ON run: `health=200`, `auth=200`, head `20260222_0012`, turn rejected with `402` and detail `Insufficient credits. Please top up your account.`, `/users/me/transactions` includes `initiated_by`, `/admin/usage/summary?bucket=day` includes `daily`, admin grant persisted with non-null `initiated_by` matching admin user id. Enforcement OFF run (after env reset + redeploy): depleted-wallet turn returned `201` with `balance_after` present and `low_balance=true`, wallet and transaction endpoints returned `200`. |
| W11-06 | Week 11 handoff document | DONE | Publish `docs/sprint_week11_handoff.md` with snapshot, artifacts, chain, carry-forwards, Week 12 gates | Handoff authored at `docs/sprint_week11_handoff.md` with completion snapshot, migration chain through `20260222_0012`, staging evidence, and Week 12 entry gates. |

## Current Focus
- Week 11 closed. Pending supervisor sign-off.

## Carry-Forward
| ID | Severity | Description |
|---|---|---|
| F68 | Low | Closed in W11-04: enforcement tests now restore `CREDIT_ENFORCEMENT_ENABLED` and clear settings cache via cleanup hooks. |

## Change Log
- 2026-02-23: Initialized Week 11 checklist and task chain W11-01..W11-06.
- 2026-02-23: Completed W11-01/W11-02/W11-03 implementation and local validation.
- 2026-02-23: Completed W11-04 (`initiated_by` user surface + F68 cleanup).
- 2026-02-23: Local validation complete: full suite `122/122` passing; Ruff critical checks (`E9,F63,F7,F82`) passing.
- 2026-02-23: Staging validation attempt run with authenticated API calls and direct DB verification. Head confirmed at `20260222_0012`, but API responses indicated deploy drift (new Week 11 fields/behavior not active). W11-05 marked `BLOCKED`.
- 2026-02-23: API redeployed from latest commit; enforcement-ON validation passed (`402` on depleted wallet), and Week 11 response contracts verified live (`initiated_by` present, admin `daily` bucket present, admin grant attribution populated).
- 2026-02-23: Enforcement reset to OFF (`CREDIT_ENFORCEMENT_ENABLED=false`) and redeployed; depleted-wallet turn returned `201` as expected. W11-05 marked `DONE`.
- 2026-02-23: Published Week 11 handoff and marked W11-06 `DONE`.
