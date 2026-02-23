# Pantheon MVP - Sprint Week 23 Checklist

Sprint window: Week 23 (Cycle 8 Part 1 - Multi-Round Orchestrator)
Owner: Codex
Reviewer: External supervising engineer
Last updated: 2026-02-23

## Sprint Goal
Replace the single-round orchestrator specialist pass with a depth-bounded round loop. The manager routes each round, runs specialists, evaluates whether to continue, and repeats up to depth 3 (cap 12 total specialist invocations). Final synthesis aggregates all rounds.

## Baseline
- Local tests at sprint open: `203` passing.
- Migration head at sprint open: `20260223_0018` (local).
- Open carry-forwards: F58 (Low), F62 (Low), F64 (Low), F70 (Medium, deployment-only).

## Definition of Done
- `evaluate_orchestrator_round()` implemented with `{"continue": bool}` JSON protocol and safe fallback.
- `route_turn()` accepts optional `prior_round_outputs` for manager context on round 2+.
- Non-streaming orchestrator turn path runs round loop (depth 3, cap 12); single `db.commit()` preserved.
- Streaming orchestrator turn path runs same round loop; emits `round_start`/`round_end` SSE events.
- Existing 203 tests pass unchanged.
- 7 new round-loop tests pass.
- Total: `210/210`.
- Ruff critical (`E9,F63,F7,F82`): passing.
- No new migrations.
- Week 23 handoff published.

---

## Week 23 Task Checklist

| ID | Task | Status | Acceptance Criteria | Evidence / Notes |
|---|---|---|---|---|
| W23-01 | Config: depth + cap settings | DONE | Two new env-backed settings added to `Settings` and `get_settings()` | Added `orchestrator_max_depth` and `orchestrator_max_specialist_invocations`. |
| W23-02 | `orchestrator_manager.py`: round evaluation + `route_turn` extension | DONE | `OrchestratorRoundDecision`, `evaluate_orchestrator_round()`, and `prior_round_outputs` param on `route_turn()` | Implemented with parse-failure fallback to `should_continue=False`. |
| W23-03 | Non-streaming turn path: round loop | DONE | `create_turn` orchestrator block replaced with round loop; single commit preserved; `Turn.assistant_output` formatted per-round | Implemented depth/cap bounded rounds and aggregated synthesis. |
| W23-04 | Streaming turn path: round loop + SSE events | DONE | `_stream_turn` orchestrator block replaced with round loop; `round_start`/`round_end` events emitted | Implemented per-round SSE events with synthesis streaming preserved. |
| W23-05 | Tests | DONE | 7 new tests pass; all 203 existing tests pass | Full suite `210/210` passing. |
| W23-06 | Docs | DONE | This checklist updated; `docs/sprint_week23_handoff.md` published at close | Published. |

---

## Task Specifications

### W23-01 — Config: depth + cap settings

**File:** `apps/api/app/core/config.py`

Add to `Settings` dataclass:
```python
orchestrator_max_depth: int          # default 3; env ORCHESTRATOR_MAX_DEPTH
orchestrator_max_specialist_invocations: int  # default 12; env ORCHESTRATOR_MAX_SPECIALIST_INVOCATIONS
```

Add to `get_settings()` return:
```python
orchestrator_max_depth=_int_env("ORCHESTRATOR_MAX_DEPTH", 3),
orchestrator_max_specialist_invocations=_int_env("ORCHESTRATOR_MAX_SPECIALIST_INVOCATIONS", 12),
```

---

### W23-02 — orchestrator_manager.py additions

**File:** `apps/api/app/services/orchestration/orchestrator_manager.py`

**1. New dataclass:**
```python
@dataclass(frozen=True)
class OrchestratorRoundDecision:
    should_continue: bool
```

**2. Extend `_build_manager_system_prompt()`:**

Add optional `prior_round_outputs: list[tuple[str, str]] | None = None` parameter.
When `prior_round_outputs` is provided and non-empty, append after the agents block:
```
Prior round specialist outputs (already covered — route for what is still missing):
[AgentName]: output text
[AgentName]: output text
```

**3. Extend `route_turn()` signature:**

Add `prior_round_outputs: list[tuple[str, str]] | None = None` (default `None`).
Pass through to `_build_manager_system_prompt()`. Callers that omit it get identical behavior to today.

**4. Add `evaluate_orchestrator_round()`:**

```python
async def evaluate_orchestrator_round(
    *,
    gateway: LlmGateway,
    manager_model_alias: str,
    user_input: str,
    all_round_outputs: list[tuple[str, str]],
    current_round: int,
    max_output_tokens: int = 128,
) -> OrchestratorRoundDecision:
```

Messages to send:
- `system`: manager persona; has seen user input and all specialist outputs so far; must decide if another round is needed.
- `user`: `user_input`
- `system`: formatted specialist outputs block (same format as synthesis: `[Name]: text`)
- `system`: `f"Round {current_round} complete. Should another round of specialist consultation run to better answer the user? Reply ONLY with valid JSON: {{\"continue\": true}} or {{\"continue\": false}}"`

Parsing:
- Parse `{"continue": bool}` from response text.
- On any parse/validation error: log warning, return `OrchestratorRoundDecision(should_continue=False)`.

The `False` fallback is intentional: a manager that cannot answer terminates the loop rather than running indefinitely.

---

### W23-03 — Non-streaming turn path: round loop

**File:** `apps/api/app/services/sessions.py` — `create_turn` endpoint, orchestrator block.

**Current structure (to replace):**

```
# PRE-LOOP (lines ~488–536): routing → orchestrator_selected_agents → selected_assignments → selected_agents
# LOOP (lines ~641–750): flat for selected_agent in selected_agents
# POST-LOOP (lines ~756–792): single synthesis call over assistant_entries
```

**New structure for orchestrator path only:**

The `roundtable`, `standalone`, and `manual` paths are **unchanged**. Only the orchestrator block is restructured.

**Step 1 — Remove** the pre-loop orchestrator routing block (the `elif room.current_mode == "orchestrator":` block that calls `route_turn()` and populates `orchestrator_selected_agents`/`selected_assignments`). Also remove the existing `> 3` truncation guard that follows.

**Step 2 — Replace** the flat `for selected_agent in selected_agents` loop with a conditional:

```python
if turn_mode == "orchestrator":
    # Multi-round loop — replaces flat agent loop
    orch_max_depth = settings.orchestrator_max_depth
    orch_max_cap = settings.orchestrator_max_specialist_invocations
    orch_round_num = 0
    orch_total_invocations = 0
    orch_all_specialist_outputs: list[tuple[str, str]] = []

    while orch_round_num < orch_max_depth and orch_total_invocations < orch_max_cap:
        orch_round_num += 1

        prior = orch_all_specialist_outputs if orch_round_num > 1 else None
        routing = await route_turn(
            agents=[assignment.agent for assignment in room_agents],
            user_input=payload.message,
            gateway=llm_gateway,
            manager_model_alias=settings.orchestrator_manager_model_alias,
            prior_round_outputs=prior,
        )
        by_key = {a.agent.agent_key.lower(): a for a in room_agents}
        round_assignments = [
            by_key[k.lower()] for k in routing.selected_agent_keys if k.lower() in by_key
        ]
        if not round_assignments:
            round_assignments = [room_agents[0]]

        remaining = orch_max_cap - orch_total_invocations
        round_assignments = round_assignments[:min(3, remaining)]
        if not round_assignments:
            break

        round_outputs: list[tuple[str, str]] = []
        for assignment in round_assignments:
            selected_agent = _room_agent_to_selected_agent(assignment)
            # ... existing specialist invocation logic (context prep, mode_executor.run_turn, usage capture) ...
            # On success: round_outputs.append((selected_agent.name, text))
            # On exception: turn_status = "partial"; append error string
            orch_total_invocations += 1

        orch_all_specialist_outputs.extend(round_outputs)
        # prior_roundtable_outputs is not used in orchestrator path; round outputs fed
        # to next round via prior_round_outputs arg to route_turn() instead.

        if orch_round_num < orch_max_depth and orch_total_invocations < orch_max_cap:
            eval_decision = await evaluate_orchestrator_round(
                gateway=llm_gateway,
                manager_model_alias=settings.orchestrator_manager_model_alias,
                user_input=payload.message,
                all_round_outputs=orch_all_specialist_outputs,
                current_round=orch_round_num,
            )
            if not eval_decision.should_continue:
                break

    # Synthesis uses all rounds combined
    specialist_outputs_for_synthesis = [
        (name, text) for name, text in orch_all_specialist_outputs
        if not text.startswith("[[agent_error]]")
    ]

else:
    # Existing flat loop (roundtable, manual, standalone) — unchanged
    for selected_agent in selected_agents:
        ...
```

**Turn.assistant_output format** for orchestrator (multiple rounds):
```
[Round 1]
AgentA: output...
AgentB: output...

[Round 2]
AgentC: output...

---

Manager synthesis:
{synthesis_text}
```

Use `orch_all_specialist_outputs` (grouped by round) to build per-round blocks:
```python
round_block_lines = []
idx = 0
for r in range(1, orch_round_num + 1):
    # track which entries belong to which round (record per-round counts during loop)
    ...
```

Simplest implementation: accumulate `per_round_entries: list[list[tuple[str, str]]]` (one inner list per round) during the round loop, then format at output time.

For `multi_agent_mode` detection in orchestrator: use `orch_total_invocations > 1` (not `len(selected_agents)`, which is no longer a flat list).

The synthesis call and manager Message persistence are **identical to W21** — just feed `specialist_outputs_for_synthesis` instead of `assistant_entries`.

Single `db.commit()` at the end — no change to F41 discipline.

---

### W23-04 — Streaming turn path: round loop + SSE events

**File:** `apps/api/app/services/sessions.py` — `_stream_turn()` inner function.

Same structural change as W23-03. Additional SSE events:

- At start of each round (before running its specialists):
  ```python
  yield _sse_event({"type": "round_start", "round": orch_round_num})
  ```

- At end of each round (after all specialists in that round complete, before evaluate call):
  ```python
  yield _sse_event({"type": "round_end", "round": orch_round_num})
  ```

`evaluate_orchestrator_round()` is a regular `await` call (not streamed) — the manager response is JSON, not prose.

Synthesis streaming is **identical to W21** — separator chunk, then stream deltas — just fed `orch_all_specialist_outputs` instead of `assistant_entries`.

Pre-loop routing block for orchestrator (lines ~1111–1159) removed, same as W23-03.

---

### W23-05 — Tests

**File:** `tests/test_orchestrator_rounds.py` (new file) or appended to `tests/test_sessions_routes.py`.

Prefer a new file to keep round-loop tests isolated. Use the same test class setup pattern as `test_sessions_routes.py` (in-memory SQLite, FakeGateway, FakeModeExecutor where needed).

**Required tests:**

| # | Name | What it verifies |
|---|---|---|
| 1 | `test_orchestrator_single_round_manager_done` | `evaluate_orchestrator_round` returns `continue=false` → loop runs exactly 1 round; synthesis covers round 1 outputs |
| 2 | `test_orchestrator_two_rounds_then_done` | evaluate returns `continue=true` after round 1, `continue=false` after round 2 → 2 rounds run; synthesis covers both |
| 3 | `test_orchestrator_depth_cap_stops_loop` | evaluate always returns `continue=true` → loop stops at `orchestrator_max_depth=3`; synthesis covers 3 rounds |
| 4 | `test_orchestrator_specialist_invocation_cap` | total invocations hit `orchestrator_max_specialist_invocations` mid-loop → loop exits; synthesis covers completed invocations only |
| 5 | `test_orchestrator_prior_outputs_fed_to_round2_routing` | `route_turn()` on round 2 receives non-empty `prior_round_outputs`; assert via mock spy on `route_turn` |
| 6 | `test_orchestrator_streaming_emits_round_events` | streaming response contains `{"type":"round_start","round":1}` and `{"type":"round_end","round":1}` events |
| 7 | `test_orchestrator_synthesis_aggregates_all_rounds` | synthesis `Message` persisted to DB contains outputs from all rounds (assert content includes specialist names from round 1 and round 2) |

**Mock pattern for evaluate:**
```python
with patch(
    "apps.api.app.api.v1.routes.sessions.evaluate_orchestrator_round",
    side_effect=[
        OrchestratorRoundDecision(should_continue=True),
        OrchestratorRoundDecision(should_continue=False),
    ],
):
    response = self.client.post(...)
```

---

## Constraints

- **F41**: single `db.commit()` per request. The round loop is entirely in-memory — no intermediate commits. Only the final Turn + Messages + LlmCallEvents commit at the end.
- **Backward compatibility**: existing W21 orchestrator tests (`test_orchestrator_turn_calls_route_turn_then_specialists_and_synthesis`, etc.) must pass without modification. When evaluate falls back to `should_continue=False` (default), behavior is identical to the single-round path.
- **`route_turn()` signature change is additive** (`prior_round_outputs=None` default). No callers break.
- **No new migrations.** All round state is in-memory per request.
- **Evaluate fallback = False** always. Never loop on manager failures.

## Verification Checklist
- [x] `203` existing tests pass.
- [x] `7` new round-loop tests pass.
- [x] Total: `210/210`.
- [x] Ruff `E9,F63,F7,F82`: passing.
- [x] Migration head unchanged: `20260223_0018`.
- [x] `docs/sprint_week23_handoff.md` published.
