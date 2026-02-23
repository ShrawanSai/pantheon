# Sprint Week 20 Handoff

## Sprint Goal
Ship production-safe per-user rate limiting for turn submission paths, covering both non-streaming and streaming endpoints.

## Completion Snapshot
- Tasks completed: `W20-01` through `W20-03`.
- Local tests at close: `190/190` passing.
- Ruff critical checks (`E9,F63,F7,F82`): passing.
- Migration head at close: `20260223_0018` (no new migration in Week 20).

## Delivered Artifacts
- W20-01 (rate limit helper and behavior):
  - Updated `apps/api/app/core/config.py` with:
    - `rate_limit_turns_per_minute` (env `RATE_LIMIT_TURNS_PER_MINUTE`, default `10`)
    - `rate_limit_turns_per_hour` (env `RATE_LIMIT_TURNS_PER_HOUR`, default `60`)
  - Added Redis sliding-window helper logic in `apps/api/app/api/v1/routes/sessions.py`:
    - `_redis_incr_with_ttl(...)`
    - `check_turn_rate_limit(...)`
  - Violation response:
    - `429`
    - JSON detail: `{ "detail": "rate limit exceeded", "retry_after_seconds": <int> }`
    - Header: `Retry-After: <int>`
  - Redis unavailable/error path logs a warning and skips the check.

- W20-02 (wire into endpoints):
  - `POST /api/v1/sessions/{session_id}/turns`
  - `POST /api/v1/sessions/{session_id}/turns/stream`
  - Both endpoints now call `check_turn_rate_limit(...)` before session DB work and turn persistence.

- W20-03 (tests):
  - Added `tests/test_rate_limiting.py` with 5 tests:
    - `test_turn_rate_limit_per_minute`
    - `test_turn_rate_limit_per_hour`
    - `test_turn_rate_limit_not_triggered_below_limit`
    - `test_streaming_turn_rate_limited`
    - `test_rate_limit_skipped_when_redis_unavailable`
  - Regression compatibility update in `tests/test_sessions_routes.py` setup:
    - default `app.state.arq_redis = None` for non-rate-limit suites to avoid incidental 429s.

- Environment contract sync:
  - Updated `docs/env_contract.md` with:
    - `RATE_LIMIT_TURNS_PER_MINUTE`
    - `RATE_LIMIT_TURNS_PER_HOUR`

## Runtime Capability At Close
Compared with Week 19 close:
- Turn endpoints now have per-user anti-spam limits:
  - burst: minute window
  - sustained: hour window
- Streaming endpoint has identical guard behavior and returns consistent `429` contract.

## Migration Chain At Close
`20260221_0001 -> 20260221_0002 -> 20260221_0003 -> 20260221_0004 -> 20260221_0005 -> 20260222_0006 -> 20260222_0007 -> 20260222_0008 -> 20260222_0009 -> 20260222_0010 -> 20260222_0011 -> 20260222_0012 -> 20260223_0013 -> 20260223_0014 -> 20260223_0015 -> 20260223_0016 -> 20260223_0017 -> 20260223_0018`

## Carry-Forward Follow-Ups
| ID | Severity | Description |
|---|---|---|
| F58 | Low | `uploaded_files.user_id` index deferred. |
| F62 | Low | `file_read` compile-per-turn behavior accepted at current throughput. |
| F64 | Low | Worker DB URL precedence remains explicit deployment policy. |
| F70 | Medium | Staging deploy drift: closes on next staging redeploy with current branch. |

## Week 21 Entry Gates
1. Keep F41 transaction discipline for orchestrator synthesis path (specialist outputs + synthesis writes + usage + debit in one commit).
2. Unlock orchestrator mode patch safely with unknown-mode guards still enforced.
3. Week 21 remains single-round orchestration + synthesis only (multi-round depth loop deferred to Cycle 8).
4. No fabricated product-owner thresholds in `docs/enforcement_production_criteria.md`.
