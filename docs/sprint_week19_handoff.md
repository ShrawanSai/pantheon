# Sprint Week 19 Handoff

## Sprint Goal
Close Cycle 6 by completing roundtable parity checks in the non-streaming path, adding explicit room mode management, and publishing Cycle 6 completion status.

## Completion Snapshot
- Tasks completed: `W19-01` through `W19-04`.
- Local tests at close: `185/185` passing.
- Ruff critical checks (`E9,F63,F7,F82`): passing.
- Migration head at close: `20260223_0018` (no new migration in Week 19).

## Delivered Artifacts
- W19-01 (roundtable non-streaming parity audit):
  - Audited `apps/api/app/api/v1/routes/sessions.py` `create_turn` path.
  - Verified parity points:
    1. `share_same_turn_outputs = turn_mode in {"roundtable", "orchestrator"}`
    2. `prior_roundtable_outputs` accumulator before loop
    3. prior outputs included in `request_messages`
    4. per-agent outputs appended back into same-turn context
    5. per-agent shared assistant message persistence with `source_agent_key`
    6. per-agent usage staging (`UsageRecorder.stage_llm_usage`)
    7. single `db.commit()` after all agents complete
  - Result: all points already present; no parity code patch required.

- W19-02 (mode change endpoint):
  - Added `PATCH /api/v1/rooms/{room_id}/mode` in `apps/api/app/api/v1/routes/rooms.py`
  - Added `RoomModeUpdateRequest` in `apps/api/app/schemas/rooms.py`
  - Allowed modes: `manual`, `roundtable`
  - Rejection:
    - `orchestrator` -> `422` with required guard detail
    - unknown modes -> `422`

- W19-03 (tests):
  - Added 5 mode tests in `tests/test_rooms_routes.py`:
    - `test_mode_patch_to_manual`
    - `test_mode_patch_to_roundtable`
    - `test_mode_patch_orchestrator_rejected`
    - `test_mode_patch_unknown_mode_rejected`
    - `test_mode_patch_foreign_room_404`
  - Added 5 roundtable non-stream tests in `tests/test_sessions_routes.py`:
    - `test_roundtable_turn_both_agents_respond`
    - `test_roundtable_turn_second_agent_sees_first_output`
    - `test_roundtable_turn_two_message_rows`
    - `test_roundtable_turn_two_usage_events`
    - `test_roundtable_turn_single_commit`

- W19-04 (Cycle 6 close-out docs):
  - Published `docs/sprint_week19_checklist.md`
  - Published `docs/sprint_week19_handoff.md`
  - Updated `docs/enforcement_production_criteria.md` Gate 3 status to PASS (implemented/tested locally)

## Cycle 6 Summary (Weeks 17-19)
- W17: SSE streaming added for turn execution with preflight enforcement and stream-close persistence.
- W18: Stripe top-up intent + webhook credit grant + admin grant endpoint delivered.
- W19: Roundtable non-streaming parity validated and room mode management endpoint delivered with orchestrator guard.

## Runtime Capability At Close
Compared with Week 18 close:
- room mode can now be switched explicitly between `manual` and `roundtable` via API
- non-streaming roundtable path has explicit parity coverage for context propagation, attribution, usage, and commit policy

## Migration Chain At Close
`20260221_0001 -> 20260221_0002 -> 20260221_0003 -> 20260221_0004 -> 20260221_0005 -> 20260222_0006 -> 20260222_0007 -> 20260222_0008 -> 20260222_0009 -> 20260222_0010 -> 20260222_0011 -> 20260222_0012 -> 20260223_0013 -> 20260223_0014 -> 20260223_0015 -> 20260223_0016 -> 20260223_0017 -> 20260223_0018`

## Carry-Forward Follow-Ups
| ID | Severity | Description |
|---|---|---|
| F58 | Low | `uploaded_files.user_id` index deferred. |
| F62 | Low | `file_read` compile-per-turn behavior accepted at current throughput. |
| F64 | Low | Worker DB URL precedence remains explicit deployment policy. |
| F70 | Medium | Staging deploy drift: staging must be redeployed with Weeks 14-19 code before parity legs can close. |

## Week 20 Entry Gates
1. Staging must be redeployed with Weeks 14-19 code before any Week 20 staging validation sequence.
2. Cycle 7 scope requires product-owner lock (candidates: orchestrator mode, admin analytics expansion, rate limiting, long-term memory).
3. `TBD_ACTIVE_USERS` and `TBD_EVENTS_PER_DAY` in `docs/enforcement_production_criteria.md` remain product-owner inputs; do not fabricate.
4. Keep F41 transaction policy locked for all new write paths.

