# Pantheon MVP - Sprint Week 2 Checklist

Sprint window: Week 2 (Data + Runtime Foundations)  
Owner: Codex  
Reviewer: External supervising engineer  
Last updated: 2026-02-21

## Sprint Goal
Complete the Week 2 preflight gates so feature work can safely start: freeze scope, add `llm_call_events` as the first Week 2 migration, and validate DB/runtime readiness before Room/Agent CRUD expansion.

## Definition of Done (Week 2)
- Week 2 scope is frozen and documented.
- `llm_call_events` migration is created and validated locally.
- `llm_call_events` migration is applied to Supabase Postgres.
- Railway API has DB env vars configured for DB-backed feature work.
- Week 2 feature implementation starts only after migration + DB readiness gates.

## Tracking Rules
- Every task has an ID and status.
- Status values: `TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`.
- After each completed task, update:
1. Task status
2. Evidence/notes
3. Change log entry

## Supervisor Checkpoint Rule
- Stop for supervisor review after each task that includes:
1. Schema change
2. Security-sensitive auth/config update
3. Architecture-impacting orchestration/runtime decisions

## Dependency Rules (Critical Path)
- W2-01 -> W2-02
- W2-02 -> W2-03
- W2-03 -> W2-04
- W2-04 + W2-05 -> W2-06
- W2-06 -> W2-07

## Week 2 Task Checklist

| ID | Task | Status | Acceptance Criteria | Evidence / Notes |
|---|---|---|---|---|
| W2-01 | Create Week 2 checklist and tracking file | DONE | `docs/sprint_week2_checklist.md` exists with task IDs, status, dependencies, follow-ups, and changelog | Created this file as Week 2 kickoff tracker. |
| W2-02 | Freeze Week 2 scope from SRS + handoff + preflight notes | DONE | Scope document lists ordered Week 2 execution gates and explicit out-of-scope items | Added `docs/week2_scope_freeze.md` with ordered execution plan and guardrails. |
| W2-03 | Define `llm_call_events` schema contract for migration | DONE | Contract includes required fields from SRS FR-BILL-002 + indexes and FK strategy decisions | Added `docs/week2_llm_call_events_contract.md` with field contract, FK/index strategy, and required cached-token fallback rule. |
| W2-04 | Add Alembic migration for `llm_call_events` | DONE | New migration revision created and `alembic upgrade head` succeeds on local migration target | Added `infra/alembic/versions/20260221_0003_llm_call_events.py`. Verified locally with `alembic upgrade head` and `alembic current` (`20260221_0003`). |
| W2-05 | Apply new migration to Supabase Postgres | DONE | Migration applied against Supabase DB; table/index presence verified via SQL query evidence | Applied with direct DB URL: `alembic upgrade head` succeeded on `PostgresqlImpl` through `20260221_0003`. Evidence query returned full `llm_call_events` column list and indexes including `uq_llm_call_events_request_id`. `alembic current` returns `20260221_0003 (head)`. |
| W2-06 | Verify Railway API DB readiness for Week 2 routes | DONE | `DATABASE_URL` and `DATABASE_POOL_URL` confirmed in Railway API service; API deploy healthy after config check | Railway API raw variable editor shows both DB vars set. Live health check confirmed `200` at `https://api-production-97ea.up.railway.app/api/v1/health`. |
| W2-07 | Begin Room/Agent CRUD implementation kickoff | DONE | Week 2 feature-start checklist satisfied and first Room/Agent CRUD implementation task opened | Completed subtracks `W2-07a` through `W2-07f` (DB foundation, room create/read/delete, room agent create/list/delete, shared auth dependency extraction) with DB-backed coverage and passing validation. |
| W2-07a | Establish DB ORM foundation for Room/Agent CRUD | DONE | `apps/api/app/db/models.py` defines ORM mappings for `users`, `rooms`, `room_agents`, `sessions`; `apps/api/app/db/session.py` provides async-capable session factory and `get_db` dependency | Added `apps/api/app/db/` package with SQLAlchemy ORM mapped classes and lazy async session/engine initialization (`DATABASE_POOL_URL` required at runtime usage). |
| W2-07b | Implement `POST /api/v1/rooms` (auth + DB write) | DONE | Endpoint exists at `/api/v1/rooms`, requires authenticated user dependency and async DB session dependency, creates owner `users` row when missing, inserts room row, and returns `201` response payload | Added route `apps/api/app/api/v1/routes/rooms.py`, wired router in `apps/api/app/main.py`, added room schemas, and validated with DB-backed tests in `tests/test_rooms_routes.py` (passes under unittest). |
| W2-07c | Implement room read routes (`GET /api/v1/rooms`, `GET /api/v1/rooms/{room_id}`) | DONE | Authenticated user can list owned non-deleted rooms and fetch owned room by ID; unauthorized/invalid access returns expected error statuses | Added list/get handlers in `apps/api/app/api/v1/routes/rooms.py`; expanded tests for read routes and W2-07b error paths (`401`, `422`, `422`) in `tests/test_rooms_routes.py`; added explicit owned+deleted GET-by-ID `404` coverage; full unittest suite passing (`12/12`). |
| W2-07d | Implement room soft-delete route (`DELETE /api/v1/rooms/{room_id}`) | DONE | Authenticated owner soft-deletes room (`deleted_at` set, `204`), and non-owned/already-deleted requests return `404` | Added delete handler in `apps/api/app/api/v1/routes/rooms.py`; DB-backed tests cover success soft-delete, not-owned `404`, already-deleted `404`; verified deleted room disappears from list/get; full suite passing (`15/15`). |
| W2-07e | Room Agent CRUD kickoff (`POST/GET/DELETE /api/v1/rooms/{room_id}/agents`) | DONE | `POST/GET/DELETE` agent routes are implemented with room ownership guardrails, uniqueness conflict handling, and DB-backed tests | Added agent routes in `apps/api/app/api/v1/routes/rooms.py` using `agent_key` as delete identifier. Added DB-backed coverage in `tests/test_rooms_routes.py` for create/list/delete success paths, ownership guard paths, and duplicate key conflict (`409`). Full suite passing (`22/22`), ruff critical rules pass. |
| W2-07f | Extract shared auth dependency (`get_current_user`) and decouple protected routes from `auth.py` route function import | DONE | Shared auth dependency module created and protected routes switched to it without behavior regression | Added `apps/api/app/dependencies/auth.py` and switched room routes to use `Depends(get_current_user)`; kept `/auth/me` behavior via shared dependency; DB-backed + scaffold suite remains green (`22/22`), ruff critical rules pass. |
| W2-08 | Publish Week 2 handoff and open Week 3 preflight checklist | DONE | Week 2 handoff document exists and Week 3 checklist is created with gate-first ordering (`F24`, `F23`, `F25`) before feature tasks | Added `docs/sprint_week2_handoff.md` and `docs/sprint_week3_checklist.md` with explicit gate dependencies and start criteria. |

## Current Focus
- Active task: Week 2 closed
- Next after active: Week 3 preflight gates (`F24` -> `F23` -> `F25`)

## Assumptions And Follow-Ups
- F20 (Week 2 gate): `llm_call_events` remains the first Week 2 migration before metering-integrated chat logic.
- F21 (Resolved 2026-02-21): Keep `users.id` as `String(64)` through MVP (store Supabase UUIDs as strings). Revisit native UUID migration in Week 3 if needed.
- F22 (Architecture): Replace orchestrator comma-split parsing with structured output contract before production orchestrator expansion.
- F23 (Runtime): Add context budget + summarization guardrails before high-turn multi-agent sessions.
- F24 (Security): Rotate Supabase service role key before broader Week 2 rollout.
- F25 (Ops): Verify separate `dev` environment strategy on Railway/Vercel to avoid production-environment coupling during Week 2 changes.
- F26 (Resolved 2026-02-21): Confirmed migration routing rule in local env: `DATABASE_URL` maps to direct Supabase host and `DATABASE_POOL_URL` maps to pooler host.
- F27 (Resolved 2026-02-21): DB URLs updated with real credentials (no bracket placeholders); direct Supabase migration apply and schema evidence queries succeeded.
- F28 (Resolved 2026-02-21): Week 2 DB layer approach locked to SQLAlchemy ORM + async-capable session dependency (`get_db`) for Room/Agent CRUD and subsequent API modules.
- F29 (Resolved 2026-02-21): DB-backed API route test strategy for Week 2: use `TestClient` with dependency overrides (`auth_me`, `get_db`) and ephemeral async SQLite (`aiosqlite`) via SQLAlchemy async session factory.
- F30 (Resolved 2026-02-21): Shared auth dependency extracted to `apps/api/app/dependencies/auth.py` (`get_current_user`) and protected routes switched off direct route-layer auth function coupling.
- F31 (Resolved 2026-02-21): Room route test class renamed to `RoomRoutesTests` to match expanded create/read/delete scope.
- F33 (Resolved 2026-02-21): Room agent delete identifier uses `agent_key` scoped under room (`DELETE /rooms/{room_id}/agents/{agent_key}`) for human-readable API semantics.
- F34 (Resolved 2026-02-21): Added missing room-agent delete branch coverage for nonexistent `agent_key` (`404 Agent not found`) to close supervisor W2-07e checkpoint gap.
- F32 (Schema/Ops): All Python-written timestamps (e.g., `deleted_at = datetime.now()`) use local wall-clock time; server-default timestamps (`created_at`, `updated_at`) use `CURRENT_TIMESTAMP` (UTC in Postgres). Fix requires `DateTime(timezone=True)` columns + migration + switching to `datetime.now(timezone.utc)` across all write paths. Address uniformly in a dedicated timestamp audit pass, not piecemeal. Also: `updated_at` is not refreshed on soft-delete - no `onupdate` hook exists. Include in same audit.

## Change Log
- 2026-02-21: Initialized Week 2 checklist and marked W2-01 done.
- 2026-02-21: Completed W2-02 by adding `docs/week2_scope_freeze.md` and freezing Week 2 execution order.
- 2026-02-21: Completed W2-03 by adding `docs/week2_llm_call_events_contract.md` (required fields, FK/index strategy, and cached-token fallback rule).
- 2026-02-21: Applied supervisor review updates to W2-03 contract: clarified `direct_session_id` semantics, added explicit `credits_burned` formula, and specified Postgres partial unique index strategy for `request_id`.
- 2026-02-21: Completed W2-04 by adding migration `20260221_0003_llm_call_events` and validating local upgrade to head with dedicated migration DB target.
- 2026-02-21: Started W2-05 and initially hit direct DB auth failure due placeholder credentials; after env fix, successfully applied migration on Supabase direct DB, verified `alembic current` (`20260221_0003`) and confirmed columns/indexes via SQL metadata queries.
- 2026-02-21: Completed W2-06 after Railway API variable confirmation (`DATABASE_URL` + `DATABASE_POOL_URL`) and live health check success (`/api/v1/health` => `200`).
- 2026-02-21: Started W2-07 Room/Agent CRUD kickoff now that Week 2 DB/runtime gates are fully satisfied.
- 2026-02-21: Resolved F21 decision for Week 2 execution: keep `users.id` as `String(64)` through MVP to avoid mid-sprint PK/FK type migration risk.
- 2026-02-21: Completed W2-07a by adding SQLAlchemy ORM DB foundation in `apps/api/app/db/models.py` and `apps/api/app/db/session.py` for upcoming Room/Agent CRUD routes.
- 2026-02-21: Completed W2-07b by implementing authenticated async `POST /api/v1/rooms`, wiring router registration, and adding DB-backed route tests (`5/5` unittest pass; ruff critical rules pass).
- 2026-02-21: Completed W2-07c by adding room read routes (`GET /api/v1/rooms`, `GET /api/v1/rooms/{room_id}`) and extending tests to cover create-route error paths plus room read access controls (`11/11` unittest pass).
- 2026-02-21: Addressed supervisor W2-07c follow-up flags by renaming room route test file to `tests/test_rooms_routes.py` and adding soft-deleted owned room GET-by-ID `404` coverage; suite now passes `12/12`.
- 2026-02-21: Completed W2-07d by adding room soft-delete endpoint (`DELETE /api/v1/rooms/{room_id}`), implementing owner+active-room guardrails, and expanding DB-backed tests (`15/15` unittest pass; ruff critical rules pass).
- 2026-02-21: Opened W2-07e for Room Agent CRUD kickoff after completing core room lifecycle routes (create/read/delete).
- 2026-02-21: Completed W2-07e by implementing room agent create/list/delete routes with ownership enforcement and unique-key conflict handling, then extending DB-backed tests; suite now passes `22/22` and ruff critical checks pass.
- 2026-02-21: Opened W2-07f to implement shared auth dependency extraction (F30) before adding more protected endpoints.
- 2026-02-21: Completed W2-07f by introducing shared auth dependency (`get_current_user`) and switching protected room routes to it while preserving `/auth/me` behavior; validation remains green (`22/22`, ruff critical checks pass).
- 2026-02-21: Added missing agent-delete not-found test (`404 Agent not found`) for W2-07e supervisor flag, then revalidated (`23/23` unittest pass; ruff critical checks pass) and closed W2-07 overall.
- 2026-02-21: Completed W2-08 by publishing Week 2 handoff and opening Week 3 checklist with mandatory preflight gates (F24, F23, F25) ahead of Week 3 feature work.
