# Sprint Week 13 Handoff

## Sprint Goal
Close Cycle 4 carry-forward items that still require implementation, lock billing attribution/enforcement conventions in code/docs, and verify staging parity status before Cycle 5 planning.

## Completion Snapshot
- Tasks targeted: `W13-01` through `W13-06`.
- Local test suite at close: `130/130` passing.
- Ruff critical checks (`E9,F63,F7,F82`): passing.
- Migration head at close: `20260223_0013`.
- Staging summary:
  - DB migration applied and verified (`tool_call_events.room_id` width updated to 64)
  - Tool event writes validated after migration (search turn wrote `tool_call_events` row successfully)
  - Week 12 admin settings parity legs still blocked by staging API deploy drift (`/api/v1/admin/settings*` returning `404`)

## Delivered Artifacts
- W13-01 (F57 schema fix):
  - Updated ORM width: `apps/api/app/db/models.py` (`ToolCallEvent.room_id` `String(64)`).
  - Added migration: `infra/alembic/versions/20260223_0013_fix_tool_call_events_room_id_width.py`.
  - Added regression assertion test: `tests/test_sessions_routes.py` (`test_tool_call_event_room_id_column_uses_64_length`).

- W13-02 (initiated_by convention lock):
  - Added convention comment above `stage_debit` in `apps/api/app/services/billing/wallet.py` documenting:
    - debits keep `initiated_by=None`
    - `user_id` + `reference_id` are the debit attribution path
    - future admin-forced debits must explicitly set `initiated_by`
    - no historical backfill

- W13-03 (enforcement production criteria doc):
  - Added `docs/enforcement_production_criteria.md`.
  - Includes trigger criteria, role-based approval, operational definition of default-on, and emergency disable path.

- W13-04 (F69 staging parity re-check):
  - Re-ran required Week 12 legs 3-7 and 12 on staging.
  - Result: still blocked by deploy drift (`404` on admin settings endpoints; `summary_used_fallback` missing in turn response).
  - F69 remains open for next staging API redeploy.

- W13-05 (staging validation for W13 changes):
  - Confirmed staging alembic head: `20260223_0013`.
  - Confirmed `tool_call_events.room_id` width on staging: `64`.
  - Confirmed tool event write path after migration via search turn:
    - turn `201`
    - `tool_call_events` row count for turn: `1`
    - latest row included `tool_name='search'`, `status='success'`, non-null latency.
  - Admin settings regression leg remains blocked by F69 deploy drift (`404`).

- W13-06 (handoff):
  - Published this handoff document.

## Runtime Capability At Close
Compared with Week 12 close, the codebase now additionally provides:
- aligned `tool_call_events.room_id` width with project ID-width convention (`64`)
- explicit codified debit attribution convention in wallet service implementation
- formal production decision framework for when enforcement should become default-on

## Migration Chain At Close
`20260221_0001 -> 20260221_0002 -> 20260221_0003 -> 20260221_0004 -> 20260221_0005 -> 20260222_0006 -> 20260222_0007 -> 20260222_0008 -> 20260222_0009 -> 20260222_0010 -> 20260222_0011 -> 20260222_0012 -> 20260223_0013`

## Carry-Forward Follow-Ups (Week 14+)
| ID | Severity | Description |
|---|---|---|
| F53 | Low | Search trigger remains heuristic (`search:` / `search for`) rather than model-driven tool dispatch. |
| F58 | Low | `uploaded_files.user_id` index remains deferred until query pressure warrants. |
| F62 | Low | `file_read` graph path compiles per turn when DB closure is needed; accepted for current throughput. |
| F64 | Low | Worker DB URL precedence (`DATABASE_POOL_URL` first) should remain explicit deployment policy. |
| F69 | Medium | Staging API deploy drift: Week 12 settings/toggle surfaces and `summary_used_fallback` response field not active on deployed API; re-run parity legs after next API redeploy. |

## Week 14 Entry Gates
1. Define Cycle 5 scope now that billing/credit controls are feature-complete.
2. Decide whether F53 (model-driven tool dispatch) becomes a Week 14 anchor.
3. Replace placeholder thresholds in `docs/enforcement_production_criteria.md` with agreed real values before any production default-on decision.
4. Keep F41 transaction policy locked for any new write paths.
