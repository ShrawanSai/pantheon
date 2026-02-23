# Sprint Week 23 Handoff

## Sprint Goal
Replace the single-round orchestrator specialist pass with a depth-bounded multi-round loop, with manager continue/stop evaluation after each round.

## Completion Snapshot
- Tasks completed: `W23-01` through `W23-06`.
- Local tests at close: `210/210` passing.
- Ruff critical checks (`E9,F63,F7,F82`): passing.
- Migration head at close: `20260223_0018`.
- New migrations this sprint: none.

## Delivered Artifacts
- W23-01 (config depth/cap):
  - Updated `apps/api/app/core/config.py`
  - Added:
    - `orchestrator_max_depth` (env: `ORCHESTRATOR_MAX_DEPTH`, default `3`)
    - `orchestrator_max_specialist_invocations` (env: `ORCHESTRATOR_MAX_SPECIALIST_INVOCATIONS`, default `12`)

- W23-02 (manager round decision + routing context):
  - Updated `apps/api/app/services/orchestration/orchestrator_manager.py`
  - Added:
    - `OrchestratorRoundDecision`
    - `evaluate_orchestrator_round(...)`
    - `route_turn(..., prior_round_outputs=...)`
  - Behavior:
    - manager parses `{"continue": bool}`
    - parse/validation failure falls back to `should_continue=False`
    - round 2+ routing includes prior-round specialist outputs context

- W23-03 (non-streaming multi-round orchestrator loop):
  - Updated `apps/api/app/api/v1/routes/sessions.py`
  - Replaced single orchestrator specialist pass with `while` loop bounded by:
    - depth (`orchestrator_max_depth`)
    - total specialist invocation cap (`orchestrator_max_specialist_invocations`)
    - manager continue decision
  - Preserved single `db.commit()` at request end.
  - Synthesis aggregates successful specialist outputs across all rounds.

- W23-04 (streaming multi-round loop + events):
  - Updated `apps/api/app/api/v1/routes/sessions.py`
  - Streaming orchestrator path now emits:
    - `{"type":"round_start","round":N}`
    - `{"type":"round_end","round":N}`
  - Uses same depth/cap/manager-stop rules as non-streaming.
  - Synthesis streaming preserved after specialist rounds.

- W23-05 (tests):
  - Updated `tests/test_sessions_routes.py`
  - Added/validated week-specific round-loop coverage:
    - `test_orchestrator_single_round_manager_done`
    - `test_orchestrator_two_rounds_then_done`
    - `test_orchestrator_depth_cap_stops_loop`
    - `test_orchestrator_specialist_invocation_cap`
    - `test_orchestrator_prior_outputs_fed_to_round2_routing`
    - `test_orchestrator_streaming_emits_round_events`
    - `test_orchestrator_synthesis_aggregates_all_rounds`

- W23-06 (docs):
  - Updated `docs/sprint_week23_checklist.md` to `DONE`.
  - Published `docs/sprint_week23_handoff.md`.

## Runtime Capability At Close
Compared with Week 22:
- Orchestrator is no longer single-pass. It now supports bounded multi-round specialist consultation.
- Both non-streaming and streaming paths share the same stop conditions:
  - manager says stop,
  - max depth reached,
  - max specialist invocations reached.
- Streaming clients can now track orchestrator progress via explicit round boundary events.

## Migration Chain At Close
Unchanged from Week 22:

`20260221_0001 -> 20260221_0002 -> 20260221_0003 -> 20260221_0004 -> 20260221_0005 -> 20260222_0006 -> 20260222_0007 -> 20260222_0008 -> 20260222_0009 -> 20260222_0010 -> 20260222_0011 -> 20260222_0012 -> 20260223_0013 -> 20260223_0014 -> 20260223_0015 -> 20260223_0016 -> 20260223_0017 -> 20260223_0018`

## Carry-Forward Follow-Ups
| ID | Severity | Description |
|---|---|---|
| F58 | Low | `uploaded_files.user_id` index deferred. |
| F62 | Low | `file_read` compile-per-turn behavior accepted at current throughput. |
| F64 | Low | Worker DB URL precedence remains explicit deployment policy. |
| F70 | Medium | Staging deploy drift; closes on staging redeploy with Week 14+ code. |

## Week 24 Entry Gates
1. Staging redeploy parity must be confirmed before closing `F70`.
2. Cycle 8 scope lock required before implementation (candidate tracks: long-term memory, orchestrator multi-hop depth policy, observability hardening).
3. Keep F41 transaction policy locked for all new write paths.
4. Do not fill product-owner placeholders in `docs/enforcement_production_criteria.md` without explicit owner input.
