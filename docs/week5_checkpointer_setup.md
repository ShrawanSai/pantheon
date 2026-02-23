# Week 5 - Checkpointer Setup And Smoke (W5-01)

Date: 2026-02-21  
Owner: Codex

## Purpose
Close W5-01 requirements:
- F42: fallback to `MemorySaver` is observable in logs.
- F43: Postgres checkpointer setup path is defined and verifiable on staging.

## Runtime Behavior
- `apps/api/app/services/orchestration/mode_executor.py` now:
  - tries `PostgresSaver.from_conn_string(DATABASE_POOL_URL)`
  - runs `checkpointer.setup()` once per process start
  - logs info when Postgres checkpointer is active
  - logs warning and falls back to `MemorySaver` if Postgres checkpointer init/setup fails

## Staging Verification Steps
1. Deploy latest `main` to Railway staging `api` service.
2. Open Railway staging API deploy logs and confirm one of:
   - success path:
     - `Using Postgres checkpointer for LangGraph turn execution.`
     - `Postgres checkpointer setup step completed.`
   - fallback path (if dependency/connection issue):
     - `Postgres checkpointer unavailable; falling back to MemorySaver. reason=...`
3. Run staging smoke:
   - `GET https://api-staging-3c02.up.railway.app/api/v1/health` -> `200`
4. Trigger one staging turn request (authenticated path) and verify no checkpointer runtime errors in logs.

## Expected Outcome
- Postgres checkpointer tables are initialized (idempotent setup call).
- Startup behavior is observable (success or fallback).
- API remains healthy and turn execution remains functional.
