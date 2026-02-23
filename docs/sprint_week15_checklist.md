# Pantheon MVP - Sprint Week 15 Checklist

Sprint window: Week 15 (Cycle 5 Part 2 - Dual-Layer Context + ReAct Tool Execution)  
Owner: Codex  
Reviewer: External supervising engineer  
Last updated: 2026-02-23

## Sprint Goal
Replace heuristic tool triggering with model-native ReAct execution and introduce dual-layer context with agent-private scratchpad traces plus shared room context visibility.

## Baseline
- Local tests at sprint open: `151` passing.
- Migration head at sprint open: `20260223_0016`.

## Entry Gate
- `F70` staging redeploy parity is the first gate before merging Week 15 to staging.

## Definition of Done (Week 15)
- Message schema supports `visibility` and `agent_key`.
- Tool execution is factory-based and request-scoped.
- `ReactAgentExecutor` is wired as the primary turn executor.
- Tool traces persist as private message rows; final assistant output remains shared.
- Dual-layer context assembly is active for room sessions.
- Week 15 tests pass and staging legs are either validated or explicitly blocked with evidence.
- Week 15 handoff is published.

## Working Rules
- Two-block execution:
- Block 1: `W15-01` to `W15-04`
- Block 2: `W15-05` to `W15-08`
- If staging is not updated, report blocker and continue local completion evidence.

## Dependency Rules
- `W15-01 -> W15-02 -> W15-03 -> W15-04 -> W15-05 -> W15-06 -> W15-07 -> W15-08`

## Week 15 Task Checklist
| ID | Task | Status | Acceptance Criteria | Evidence / Notes |
|---|---|---|---|---|
| W15-01 | Message schema: visibility + tool role support | IN_REVIEW | Migration `20260223_0017_messages_visibility_and_tool_role.py`; ORM `Message.visibility` + `Message.agent_key`; role compatibility with tool traces | Implemented in `infra/alembic/versions/20260223_0017_messages_visibility_and_tool_role.py` and `apps/api/app/db/models.py`; tests in `tests/test_message_schema.py`. |
| W15-02 | Tool factory pattern (`react_tools.py`) | IN_REVIEW | Request-scoped tool closures for search/file with staged telemetry and no internal commit | Implemented in `apps/api/app/services/tools/react_tools.py` with `ToolInvocationTelemetry`, `make_web_search_tool`, `make_read_file_tool`. |
| W15-03 | `ReactAgentExecutor` + executor wiring | IN_REVIEW | New executor path active; direct fallback when tools are unavailable; legacy executor retained for rollback | Implemented in `apps/api/app/services/orchestration/react_executor.py`; `get_mode_executor()` now returns `ReactAgentExecutor` via `apps/api/app/services/orchestration/mode_executor.py`. |
| W15-04 | Persist private tool scratchpad messages | IN_REVIEW | Tool call + tool result persisted as private rows, final output shared, single commit policy preserved | Implemented in `apps/api/app/api/v1/routes/sessions.py` with `visibility='private'` for tool trace rows and `visibility='shared'` for final assistant output. |
| W15-05 | Dual-layer context assembly | IN_REVIEW | Shared + current-agent-private context assembled chronologically with other-agent attribution labels and private cutoff config | Implemented in `apps/api/app/api/v1/routes/sessions.py`; config added in `apps/api/app/core/config.py` as `AGENT_PRIVATE_CONTEXT_TURNS_KEEP`. |
| W15-06 | Tests for ReAct + dual-layer persistence/context | IN_REVIEW | ReAct executor tests, private/shared persistence tests, and cross-agent attribution coverage pass | Added `tests/test_react_executor.py`; updated `tests/test_sessions_routes.py`; `tests/test_standalone_sessions.py` and room regressions passing. |
| W15-07 | Staging validation + F70 recheck | BLOCKED | Run F70 closure legs + Week 15 tool legs on staging; confirm alembic head `20260223_0017` | Current staging output from `tmp_w15_staging_validate.py`: `POST /api/v1/agents` and `GET /api/v1/agents` return `404` (deploy drift). Regression legs `/api/v1/admin/settings` and `/api/v1/admin/usage/summary?bucket=day` return `200`. |
| W15-08 | Week 15 handoff | DONE | Publish handoff with completion snapshot, artifacts, runtime delta, migration chain, carry-forwards, and Week 16 gates | Published `docs/sprint_week15_handoff.md`. |

## Current Focus
- Complete handoff publication and provide supervisor-ready status with staging blocker evidence for `W15-07`.

## Carry-Forward At Week 15 Entry
| ID | Severity | Description |
|---|---|---|
| F53 | Low | Heuristic tool trigger legacy path (targeted for closure by ReAct rollout). |
| F58 | Low | `uploaded_files.user_id` index deferred. |
| F62 | Low | File-read path compilation behavior accepted at current throughput. |
| F64 | Low | Worker DB URL precedence remains explicit deployment policy. |
| F70 | Medium | Staging deploy drift on Week 14/15 agent endpoints (`/api/v1/agents*` returning `404`). |

## Change Log
- 2026-02-23: Initialized Week 15 checklist and recorded local implementation evidence for `W15-01` through `W15-06`.
- 2026-02-23: Logged staging blocker evidence for `W15-07` from `tmp_w15_staging_validate.py`.
