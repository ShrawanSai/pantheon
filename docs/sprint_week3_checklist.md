# Pantheon MVP - Sprint Week 3 Checklist

Sprint window: Week 3 (Sessions + LLM Loop Foundation)  
Owner: Codex  
Reviewer: External supervising engineer  
Last updated: 2026-02-21

## Sprint Goal
Establish the first end-to-end session-to-turn execution loop on production modules without violating Week 3 security/runtime gates.

## Definition of Done (Week 3)
- Week 3 gates `F24` and `F23` are completed before feature code begins; `F25` strategy is locked before feature coding and fully closed after staging endpoint provisioning is confirmed.
- Session route foundation exists and is DB-backed.
- LLM gateway baseline is integrated with a turn write path.
- Context budget policy is enforced in the first turn execution path.

## Tracking Rules
- Every task has an ID and status.
- Status values: `TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`.
- After each completed task, update:
1. Task status
2. Evidence/notes
3. Change log entry

## Supervisor Checkpoint Rule
- Stop for supervisor review after each task that includes:
1. Security changes (keys/auth policy/permission model)
2. New route groups (sessions/turns/messages)
3. Orchestration/runtime behavior changes

## Dependency Rules (Critical Path)
- W3-01 -> W3-02
- W3-02 -> W3-03
- W3-03 -> W3-04
- W3-04 -> production/staging deployment of W3-05+
- W3-05 -> W3-06
- W3-06 -> W3-07
- Local implementation/testing for W3-05/W3-06/W3-07 may proceed in parallel while W3-04 provisioning is pending user-side cloud setup confirmation.

## Week 3 Task Checklist

| ID | Task | Status | Acceptance Criteria | Evidence / Notes |
|---|---|---|---|---|
| W3-01 | Create Week 3 checklist and gate plan | DONE | `docs/sprint_week3_checklist.md` exists with gate-first sequencing and dependencies | Initialized Week 3 tracker and locked gate-first dependency order. |
| W3-02 | Gate C: rotate Supabase service role key (F24) | DONE | Old key invalidated, new key applied in local + Railway/Vercel + CI contexts, auth smoke checks pass | User confirmed key rotation completed. Runtime smoke evidence: `GET /api/v1/health` => `200`; unauthenticated `GET /api/v1/auth/me` => `401` (route reachable and enforcing auth). |
| W3-03 | Gate: lock context budget + summarization design (F23) | DONE | Design doc records token budget policy, trigger thresholds, summarize/truncate behavior, and failure handling | Updated `docs/week3_context_budget_design.md` with supervisor-requested clarifications: settings source for max output tokens, summary turn reset rule, unresolved-turn definition, semantic-anchor pruning rule, required `session_summaries` migration, and explicit observability sink (`turn_context_audit`). |
| W3-04 | Gate: decide dev environment strategy (F25) | DONE | Decision doc records chosen strategy and required environment isolation steps | Staging stack confirmed: Supabase staging (`hekyjuygkaqzpxgebbmi`) with auth URL + callback configured; Railway staging API (`api-staging-3c02.up.railway.app`) returns `/api/v1/health=200` and unauthenticated `/api/v1/auth/me=401`; Railway staging worker (`worker-staging-d144.up.railway.app`) logs healthy worker + Redis connection; Vercel Preview deployment ready and pointed to staging values; staging DB migrated to `20260221_0004 (head)` via Alembic. |
| W3-05 | Implement session route foundation | DONE | Session create/list/soft-delete routes added with ownership checks + DB-backed tests | Added `apps/api/app/api/v1/routes/sessions.py` endpoints: `POST /rooms/{room_id}/sessions`, `GET /rooms/{room_id}/sessions`, `DELETE /rooms/{room_id}/sessions/{session_id}`; added `tests/test_sessions_routes.py` coverage (`test_create_session_for_owned_room`, `test_create_session_returns_404_for_not_owned_room`, `test_delete_session_soft_deletes_and_hides_from_list`). |
| W3-06 | Implement LLM gateway baseline + usage hook stub | DONE | `services/llm/gateway.py` performs request/response flow with structured return and usage metadata capture points | Implemented `apps/api/app/services/llm/gateway.py` (`GatewayRequest/Response/Usage`, async `OpenRouterLlmGateway.generate`) and `apps/api/app/services/usage/recorder.py` usage hook stub; wired gateway + recorder into turn route; verified by `test_create_turn_writes_turn_messages_and_audit`. |
| W3-07 | Implement first turn execution path with context guardrail | DONE | `POST /turns`-style path writes turn/messages and enforces approved context budget policy | Added `POST /api/v1/sessions/{session_id}/turns` with context manager enforcement, turn+message writes, summary/audit persistence, and usage hook call; added migration `infra/alembic/versions/20260221_0004_session_summaries_context_audit.py`; tests now cover success path, overflow rejection (`422 context_budget_exceeded`), and second-turn increment behavior. Known limitation documented: summary generation is deterministic truncation (structured summary fields deferred). |

## Current Focus
- Active task: Week 3 closeout and handoff
- Next after active: Supervisor approval checkpoint for final Week 3 closure

## Assumptions And Follow-Ups
- F22 (Architecture): manager routing output must be structured (no comma-split parser fallback in production path).
- F32 (Schema/Ops): timezone and `updated_at` behavior audit should be scheduled after Week 3 critical path unless it blocks implementation.
- F35 (Code Structure): `_get_owned_active_room_or_404` is duplicated in `rooms.py` and `sessions.py`; extract shared room-ownership guard before adding more route groups.
- F36 (Concurrency): `turn_index` is derived from `max(turn_index) + 1`; concurrent turn creation can race and raise unique-constraint conflicts. Add transaction-safe sequencing or IntegrityError handling in a follow-up.
- F37 (Context Quality): summarization currently uses deterministic truncation and stores empty structured summary arrays; replace with LLM-backed structured summarization before relying on those fields in analytics/billing workflows.

## Change Log
- 2026-02-21: Initialized Week 3 checklist with mandatory gate-first execution order from Week 2 handoff.
- 2026-02-21: Completed W3-02 after user-confirmed Supabase service role key rotation and production smoke checks (`/health` 200, `/auth/me` unauthenticated 401).
- 2026-02-21: Started W3-03 context budget + summarization design draft for supervisor/user approval.
- 2026-02-21: Completed W3-03 by applying required clarifications from supervisor review to `docs/week3_context_budget_design.md` and locking implementation-level rules.
- 2026-02-21: Started W3-04 dev environment strategy decision to close F25 before Week 3 feature coding.
- 2026-02-21: Added `docs/week3_dev_environment_strategy.md` draft with concrete setup/rollout rules for F25 approval.
- 2026-02-21: Completed W3-05 locally with DB-backed session routes and tests in `tests/test_sessions_routes.py`.
- 2026-02-21: Completed W3-06 by implementing OpenRouter-backed LLM gateway baseline and usage recorder hook integration into the turn path.
- 2026-02-21: Completed W3-07 by adding guarded turn execution with context overflow handling, summary/context audit persistence, migration `20260221_0004`, and end-to-end route tests.
- 2026-02-21: Revalidated suite after W3 changes: `python -m unittest discover -s tests -p "test_*.py" -v` => 28/28 passing; `python -m ruff check ... --select E9,F63,F7,F82` => all checks passed.
- 2026-02-21: Added supervisor-requested W3-07 coverage gaps in `tests/test_sessions_routes.py`: list sessions behavior, not-owned room delete path for sessions (`404`), and second turn write path (`turn_index=2`, 4 messages total).
- 2026-02-21: Documented known W3 limitations and deferments as follow-ups: F35 (shared room guard extraction), F36 (turn index race), F37 (structured summarization not yet implemented).
- 2026-02-21: Closed W3-04 by validating staging environment end-to-end: Supabase auth URLs configured, Railway staging API/worker healthy, Vercel Preview redeployed with staging integration, and staging DB migrated/verified at `20260221_0004 (head)`.
