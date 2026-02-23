# Pantheon MVP - Week 3 Dev Environment Strategy (F25)

Date: 2026-02-21  
Owner: Codex  
Status: Approved for local implementation; pending user-side staging provisioning confirmation for closure

## 1) Problem
Current development can hit production-backed services directly (DB/auth/secrets), which increases risk of data corruption, accidental cost burn, and unsafe testing.

## 2) Decision
Adopt **isolated staging-by-default** for Week 3 onward:
- Backend deploy target for development/testing: Railway staging environment/service
- Frontend deploy target for development/testing: Vercel preview/staging
- Data/auth/storage target for development/testing: separate Supabase staging project
- Production is write-protected operationally (no routine feature testing against prod)

## 3) Why This Option
- Lowest operational risk while preserving realistic integration testing.
- Avoids local-only drift from deployed behavior.
- Keeps auth/provider/queue integrations testable before production release.

## 4) Required Setup
1. Supabase:
   - create staging project
   - configure auth redirect URLs for staging frontend
   - create staging storage bucket(s) matching production names
   - provision staging API keys/secrets
2. Railway:
   - create/use staging environment (or branch service set)
   - set staging vars (`DATABASE_URL`, `DATABASE_POOL_URL`, `SUPABASE_*`, `REDIS_URL`, `OPENROUTER_*`)
   - run `alembic upgrade head` against staging `DATABASE_URL` before deploying DB-dependent feature routes
   - ensure a staging worker service is provisioned if background jobs are enabled in Week 3/4
3. Vercel:
   - ensure Preview environment vars point to staging backend + staging Supabase
4. CI:
   - keep unit tests self-contained
   - optional gated integration job can target staging only

## 5) Operational Rules
- Rule 1: feature branches test against staging, not production.
- Rule 2: production secrets are never reused in local `.env` for feature development.
- Rule 3: data migrations run on staging first; production migration runs only after explicit approval.
- Rule 4: production smoke checks are read-only and minimal.

## 6) Rollout Plan
1. Approve this strategy.
2. Provision staging Supabase and staging Railway variables.
3. Point local and preview env files at staging endpoints.
4. Run Week 3 session-route development against staging.
5. Add a short runbook section for promotion staging -> production.

## 7) Exit Criteria For F25
- Strategy approved.
- Staging service endpoints exist and are documented.
- Team confirms Week 3 feature work uses staging by default.
- Closure note: endpoint provisioning is a manual cloud operation (Supabase/Railway/Vercel dashboards) and must be confirmed by user/supervisor.
