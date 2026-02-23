# Sprint Week 18 Handoff

## Sprint Goal
Implement Stripe-backed wallet top-up so users can fund credits, webhooks can grant credits safely/idempotently, and admins can apply manual grants.

## Completion Snapshot
- Tasks completed: `W18-01` through `W18-05`.
- Local tests at close: `175/175` passing.
- Ruff critical checks (`E9,F63,F7,F82`): passing.
- Migration head at close: `20260223_0018` (no new migration in Week 18).

## Delivered Artifacts
- W18-01 (config + dependency):
  - Added Stripe/payment settings in `apps/api/app/core/config.py`:
    - `stripe_secret_key`
    - `stripe_webhook_secret`
    - `top_up_min_usd`
    - `top_up_max_usd`
    - `credits_per_usd`
  - Added dependency: `requirements.txt` (`stripe>=10.0.0`)
  - Updated env docs: `docs/env_contract.md`

- W18-02 (top-up intent endpoint):
  - Added `POST /api/v1/users/me/wallet/top-up` in `apps/api/app/api/v1/routes/users.py`
  - Validation: `1.00 <= amount_usd <= 500.00`
  - Credits conversion: `round(amount_usd * credits_per_usd, 2)`
  - PaymentIntent integration via service helper: `apps/api/app/services/billing/stripe_client.py`
  - New schemas: `WalletTopUpCreate`, `WalletTopUpRead` in `apps/api/app/schemas/users.py`

- W18-03 (webhook receiver):
  - Added `POST /webhooks/stripe` in `apps/api/app/api/v1/routes/webhooks.py`
  - Signature verification path using Stripe helper (`construct_webhook_event`)
  - Local-only shortcut when webhook secret unset (warning logged)
  - Handles only `payment_intent.succeeded`
  - Idempotency via `CreditTransaction.reference_id == payment_intent_id`
  - Grants credits through `WalletService.stage_grant(...)` + `db.commit()`
  - Router registered in `apps/api/app/main.py`

- W18-04 (admin grant endpoint):
  - Added `POST /api/v1/admin/users/{user_id}/wallet/grant` in `apps/api/app/api/v1/routes/admin.py`
  - Uses existing admin auth guard
  - Returns credits granted + post-grant balance
  - Added `AdminUserGrantResponse` schema in `apps/api/app/schemas/admin.py`

- W18-05 (tests):
  - Added `tests/test_topup.py` with 8 tests:
    - top-up success with mocked PaymentIntent
    - min/max validation
    - 503 when Stripe is not configured
    - webhook grant success
    - webhook idempotency
    - webhook bad signature
    - admin grant balance update

## Runtime Capability At Close
Compared with Week 17 close:
- users can request Stripe payment intents for wallet top-up
- webhook-driven credit grants are idempotent and audited by reference ID
- admins can manually grant user credits through a dedicated API

## Migration Chain At Close
`20260221_0001 -> 20260221_0002 -> 20260221_0003 -> 20260221_0004 -> 20260221_0005 -> 20260222_0006 -> 20260222_0007 -> 20260222_0008 -> 20260222_0009 -> 20260222_0010 -> 20260222_0011 -> 20260222_0012 -> 20260223_0013 -> 20260223_0014 -> 20260223_0015 -> 20260223_0016 -> 20260223_0017 -> 20260223_0018`

## Carry-Forward Follow-Ups
| ID | Severity | Description |
|---|---|---|
| F58 | Low | `uploaded_files.user_id` index deferred. |
| F62 | Low | `file_read` compile-per-turn behavior accepted at current throughput. |
| F64 | Low | Worker DB URL precedence remains explicit deployment policy. |
| F70 | Medium | Staging deploy drift persists until next staging redeploy. |

## Week 19 Entry Gates
1. Keep Week 19 scope limited to Round Table parity/gap-filling and mode patch endpoint.
2. Keep orchestrator mode patch guarded (`422`) per Cycle 6 prescription.
3. Preserve F41 policy: one commit per turn path, including multi-agent roundtable runs.
4. Keep Stripe secrets in env only; never hardcode keys.

