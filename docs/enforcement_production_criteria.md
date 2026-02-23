# Enforcement Production Criteria

## Purpose
This document defines the decision framework for promoting `CREDIT_ENFORCEMENT_ENABLED=true` as the **production default**.

This is a trigger-definition document, not a rollout procedure. Rollout/rollback mechanics are documented in `docs/enforcement_rollout.md`.

## Trigger Criteria
All criteria below must be satisfied before changing the production default.

### 1. Minimum Active User Count (threshold gate)
- Metric: active users over a rolling 30-day window.
- Placeholder threshold: `TBD_ACTIVE_USERS`.
- Status: must be met continuously for at least 2 consecutive weeks.

### 2. Minimum Billing Event Volume Per Day (throughput gate)
- Metric: average `llm_call_events` volume per day over a rolling 14-day window.
- Placeholder threshold: `TBD_EVENTS_PER_DAY`.
- Status: must be met continuously for at least 14 days.

### 3. Wallet Top-Up Flow Live and Tested (binary gate)
- Requirement: top-up flow exists in production and has a passing end-to-end test path.
- Status: pass/fail.

### 4. Warn-Only Observation Window (observation gate)
- Requirement: at least one full week of warn-only production data with `low_balance` visibility.
- Evidence source: admin usage/reporting surfaces and operational logs.
- Status: pass/fail.

### 5. Rollback Readiness Verified (binary gate)
- Requirement: rollback procedure from `docs/enforcement_rollout.md` has been exercised on staging.
- Status: pass/fail.

## Approval Authority
The default-on decision requires approval from role-based owners:
- Product Owner
- Engineering Lead

## Operational Definition of Default-On
"Default-on" means:
1. Production environment sets `CREDIT_ENFORCEMENT_ENABLED=true`.
2. Deployment is rolled out.
3. Smoke verification passes, including:
   - `GET /api/v1/admin/settings` returns `enforcement_source: "config"`
   - `enforcement_enabled: true`

## Emergency Disable Path
If enforcement must be disabled quickly:
1. Use runtime rollback endpoint sequence from `docs/enforcement_rollout.md` (`DELETE /api/v1/admin/settings/enforcement` and/or set override via PATCH as needed).
2. Revert production env default to `CREDIT_ENFORCEMENT_ENABLED=false` and redeploy for persistent warn-only behavior.
