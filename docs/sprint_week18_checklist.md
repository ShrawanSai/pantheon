# Pantheon MVP - Sprint Week 18 Checklist

Sprint window: Week 18 (Cycle 6 Part 2 - Stripe Wallet Top-Up)  
Owner: Codex  
Reviewer: External supervising engineer  
Last updated: 2026-02-23

## Sprint Goal
Ship Stripe-backed credit top-up flow (intent + webhook + admin grant) to close wallet funding as the remaining hard gate before enforcement default-on.

## Baseline
- Local tests at sprint open: `167` passing.
- Migration head at sprint open: `20260223_0018`.

## Definition of Done
- Stripe config/env support added.
- User top-up intent endpoint returns `client_secret` and computed credits.
- Webhook endpoint verifies signature (or uses local-only shortcut when secret unset), grants credits idempotently.
- Admin grant endpoint exists on `/admin/users/{user_id}/wallet/grant`.
- Required Week 18 tests (8) pass.
- Week 18 handoff is published.

## Week 18 Task Checklist
| ID | Task | Status | Acceptance Criteria | Evidence / Notes |
|---|---|---|---|---|
| W18-01 | Config + Stripe dependency | DONE | Add stripe keys/settings and dependency; update env contract | Updated `apps/api/app/core/config.py`, `requirements.txt` (`stripe>=10.0.0`), and `docs/env_contract.md`. |
| W18-02 | Top-up intent endpoint | DONE | `POST /api/v1/users/me/wallet/top-up` validates range, computes credits, creates PaymentIntent, returns `client_secret` | Implemented in `apps/api/app/api/v1/routes/users.py`; helper in `apps/api/app/services/billing/stripe_client.py`; schemas in `apps/api/app/schemas/users.py`. |
| W18-03 | Stripe webhook receiver | DONE | `POST /webhooks/stripe` verifies signature, handles `payment_intent.succeeded`, idempotent grant by `reference_id` | Implemented in `apps/api/app/api/v1/routes/webhooks.py`, registered in `apps/api/app/main.py`. |
| W18-04 | Admin grant endpoint | DONE | `POST /api/v1/admin/users/{user_id}/wallet/grant` grants credits with admin auth and returns new balance | Implemented in `apps/api/app/api/v1/routes/admin.py`; response schema added in `apps/api/app/schemas/admin.py`. |
| W18-05 | Tests | DONE | 8 required tests covering top-up, webhook, idempotency, bad signature, and admin grant | Added `tests/test_topup.py` (8 tests). |

## Verification
- Full suite: `175/175` passing.
- Ruff critical (`E9,F63,F7,F82`): passing.
- Alembic head unchanged: `20260223_0018`.

## Carry-Forwards At Week 18 Close
| ID | Severity | Description |
|---|---|---|
| F58 | Low | `uploaded_files.user_id` index deferred. |
| F62 | Low | `file_read` compile-per-turn behavior accepted at current throughput. |
| F64 | Low | Worker DB URL precedence remains explicit deployment policy. |
| F70 | Medium | Staging deploy drift (Week 14+ routes/migrations not yet active on staging deployment). |

