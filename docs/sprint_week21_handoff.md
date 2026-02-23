# Sprint Week 21 Handoff

## Sprint Goal
Complete orchestrator mode MVP behavior by adding manager synthesis in both turn paths, unlocking orchestrator mode patching, and enforcing an explicit specialist invocation cap.

## Completion Snapshot
- Tasks completed: `W21-01` through `W21-04`.
- Local tests at close: `196/196` passing.
- Ruff critical checks (`E9,F63,F7,F82`): passing.
- Migration head at close: `20260223_0018` (no migration in Week 21).

## Delivered Artifacts
- W21-01 (manager synthesis generation):
  - Updated `apps/api/app/services/orchestration/orchestrator_manager.py`:
    - `build_orchestrator_synthesis_messages(...)`
    - `generate_orchestrator_synthesis(...)`
    - `OrchestratorSynthesisResult`
  - Synthesis function uses manager prompt + specialist outputs and returns text + `GatewayResponse` for usage attribution.

- W21-02 (wire synthesis into both turn paths):
  - Updated `apps/api/app/api/v1/routes/sessions.py`:
    - Non-stream orchestrator path calls synthesis after specialist loop when specialist outputs exist.
    - Streaming orchestrator path emits synthesis separator and streams synthesis deltas.
    - Manager synthesis persisted as shared `Message` with:
      - `agent_key="manager"`
      - `source_agent_key="manager"`
      - `agent_name="Manager"`
    - Additional synthesis usage staged via `UsageRecorder.stage_llm_usage(...)` and debited via `WalletService.stage_debit(...)` in the same turn transaction.
    - `Turn.assistant_output` now appends:
      - `---`
      - `Manager synthesis:` block.

- W21-03 (mode patch unlock + cap):
  - Updated `apps/api/app/api/v1/routes/rooms.py`:
    - `PATCH /api/v1/rooms/{room_id}/mode` now allows `manual`, `roundtable`, `orchestrator`.
    - Unknown mode guard now returns:
      - `{"detail": "unsupported mode; allowed: manual, roundtable, orchestrator"}`
  - Updated `apps/api/app/api/v1/routes/sessions.py`:
    - Added orchestrator specialist cap guard in both turn paths:
      - warns and truncates to first 3 assignments.

- W21-04 (tests):
  - Updated `tests/test_rooms_routes.py`:
    - `test_mode_patch_orchestrator_allowed`
    - strengthened unknown-mode detail assertion.
  - Added orchestrator completion tests in `tests/test_sessions_routes.py`:
    - `test_orchestrator_turn_calls_route_turn_then_specialists_and_synthesis`
    - `test_orchestrator_synthesis_message_persisted`
    - `test_orchestrator_synthesis_in_turn_output`
    - `test_orchestrator_invocation_cap_truncates_to_3`
    - `test_orchestrator_empty_specialist_outputs_skips_synthesis`
    - `test_orchestrator_synthesis_in_stream_output`
  - Updated `tests/test_standalone_sessions.py` history expectation for orchestrator room sessions to include manager synthesis message row.

## Runtime Capability At Close
Compared with Week 20 close:
- Orchestrator turns now produce a manager-level consolidated synthesis in both non-streaming and streaming paths.
- Orchestrator synthesis is fully attributed/persisted/charged within the same turn commit.
- Room mode patch endpoint now supports explicit orchestrator activation.
- Specialist invocation cap has explicit endpoint-side enforcement even if manager routing behavior changes later.

## Migration Chain At Close
`20260221_0001 -> 20260221_0002 -> 20260221_0003 -> 20260221_0004 -> 20260221_0005 -> 20260222_0006 -> 20260222_0007 -> 20260222_0008 -> 20260222_0009 -> 20260222_0010 -> 20260222_0011 -> 20260222_0012 -> 20260223_0013 -> 20260223_0014 -> 20260223_0015 -> 20260223_0016 -> 20260223_0017 -> 20260223_0018`

## Carry-Forward Follow-Ups
| ID | Severity | Description |
|---|---|---|
| F58 | Low | `uploaded_files.user_id` index deferred. |
| F62 | Low | `file_read` compile-per-turn behavior accepted at current throughput. |
| F64 | Low | Worker DB URL precedence remains explicit deployment policy. |
| F70 | Medium | Staging deploy drift closes on next staging redeploy with current branch. |

## Week 22 Entry Gates
1. Keep admin analytics endpoints behind admin auth with strict date-window filtering and deterministic aggregation.
2. Use `llm_call_events` as analytics source-of-truth for token and credit aggregation.
3. Do not block Week 22 code completion on staging if redeploy is delayed; log F70 status explicitly.
4. Keep F41 transaction discipline for any new write paths (none expected in W22 analytics read endpoints).
