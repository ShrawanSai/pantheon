# Pantheon MVP - Sprint Week 20 Checklist

Sprint window: Week 20 (Cycle 7 Part 1 - Per-User Rate Limiting)  
Owner: Codex  
Reviewer: External supervising engineer  
Last updated: 2026-02-23

## Sprint Goal
Add per-user Redis-backed rate limiting on both turn submission endpoints (`/turns` and `/turns/stream`) to protect backend capacity and prevent request spam.

## Baseline
- Local tests at sprint open: `185` passing.
- Migration head at sprint open: `20260223_0018`.

## Definition of Done
- Per-minute and per-hour turn limits are enforced for authenticated users.
- Both turn endpoints apply the same rate-limit check.
- Rate-limit breaches return `429` with `Retry-After` and retry metadata.
- Redis-unavailable fallback skips limiting (warn-only) without request failure.
- Week 20 handoff is published.

## Week 20 Task Checklist
| ID | Task | Status | Acceptance Criteria | Evidence / Notes |
|---|---|---|---|---|
| W20-01 | Rate limit middleware/helper | DONE | Sliding window counters via Redis with minute/hour keys; skip safely when Redis is unavailable | Added `check_turn_rate_limit(...)` in `apps/api/app/api/v1/routes/sessions.py`, with keys `ratelimit:{user_id}:turns:{bucket}` for minute/hour buckets, `INCR` + TTL behavior, and warning fallback when Redis/pool is unavailable. |
| W20-02 | Wire into both turn endpoints | DONE | Non-streaming and streaming endpoints enforce same guard before DB work | Added explicit calls in both `POST /sessions/{session_id}/turns` and `POST /sessions/{session_id}/turns/stream` before session lookup/persistence logic. |
| W20-03 | Tests | DONE | 5 tests: minute/hour limits, below-limit pass, streaming path, redis-unavailable skip | Added `tests/test_rate_limiting.py` with 5 passing tests covering all required cases including `Retry-After` semantics. |

## Verification
- Week 20 new tests: `5/5` passing.
- Full test suite: `190/190` passing.
- Ruff critical (`E9,F63,F7,F82`): passing.
- Alembic head unchanged: `20260223_0018`.

## Carry-Forwards At Week 20 Close
| ID | Severity | Description |
|---|---|---|
| F58 | Low | `uploaded_files.user_id` index deferred. |
| F62 | Low | `file_read` compile-per-turn behavior accepted at current throughput. |
| F64 | Low | Worker DB URL precedence remains explicit deployment policy. |
| F70 | Medium | Staging deploy drift closes on next staging redeploy with current branch. |
