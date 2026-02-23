# Sprint Week 15 Handoff

## Sprint Goal
Deliver dual-layer context and model-native ReAct tool execution so each agent has private tool scratchpad traces while shared outputs remain visible across room participants.

## Completion Snapshot
- Tasks targeted: `W15-01` through `W15-08`.
- Local test suite at close: `160/160` passing.
- Ruff critical checks (`E9,F63,F7,F82`): passing.
- Migration head at close: `20260223_0017`.
- Staging summary:
  - `GET /api/v1/health`: `200`
  - `GET /api/v1/auth/me`: `200`
  - `POST /api/v1/agents`: `404`
  - `GET /api/v1/agents`: `404`
  - `GET /api/v1/admin/settings`: `200`
  - `GET /api/v1/admin/usage/summary?bucket=day`: `200`
  - Outcome: staging still not serving Week 14/15 agent routes; `W15-07` remains blocked by deploy drift (`F70`).

## Delivered Artifacts
- W15-01 (message visibility schema):
  - Migration: `infra/alembic/versions/20260223_0017_messages_visibility_and_tool_role.py`
  - ORM updates: `apps/api/app/db/models.py` (`Message.visibility`, `Message.agent_key`)
  - Tests: `tests/test_message_schema.py`

- W15-02 (tool factories for request-scoped ReAct tools):
  - New service: `apps/api/app/services/tools/react_tools.py`
  - Includes tool closures and telemetry capture model (`ToolInvocationTelemetry`)

- W15-03 (ReAct executor implementation + wiring):
  - New executor: `apps/api/app/services/orchestration/react_executor.py`
  - Executor DI switch: `apps/api/app/services/orchestration/mode_executor.py` now returns `ReactAgentExecutor`
  - Legacy `LangGraphModeExecutor` retained in code for rollback path

- W15-04 (private scratchpad persistence for tool traces):
  - Route persistence updates: `apps/api/app/api/v1/routes/sessions.py`
  - Tool calls/results persisted as `visibility='private'` rows with `agent_key`
  - Final assistant output persisted as `visibility='shared'`

- W15-05 (dual-layer context assembly):
  - Context assembly updated in `apps/api/app/api/v1/routes/sessions.py`
  - Shared + current-agent-private message merge and chronological interleave
  - Other-agent shared assistant outputs labeled for attribution
  - Config added: `apps/api/app/core/config.py` (`AGENT_PRIVATE_CONTEXT_TURNS_KEEP`)

- W15-06 (test coverage):
  - New: `tests/test_react_executor.py`
  - Updated: `tests/test_sessions_routes.py`
  - Existing standalone/room suites validated with Week 15 refactor

- W15-07 (staging validation):
  - Runner: `tmp_w15_staging_validate.py`
  - Recorded blocker evidence for F70 (`/api/v1/agents*` 404) with passing regression endpoints.

- W15-08 (handoff):
  - Published this document and `docs/sprint_week15_checklist.md`.

## Runtime Capability At Close
Compared with Week 14 close, the backend now additionally supports:
- message-level visibility semantics (`shared` vs `private`)
- request-scoped ReAct tool wrappers for search and file read paths
- ReAct-first turn executor with direct-call fallback when tools are unavailable
- persisted private tool traces as first-class session messages
- dual-layer room-context assembly that mixes shared messages with agent-private scratchpad context

## Migration Chain At Close
`20260221_0001 -> 20260221_0002 -> 20260221_0003 -> 20260221_0004 -> 20260221_0005 -> 20260222_0006 -> 20260222_0007 -> 20260222_0008 -> 20260222_0009 -> 20260222_0010 -> 20260222_0011 -> 20260222_0012 -> 20260223_0013 -> 20260223_0014 -> 20260223_0015 -> 20260223_0016 -> 20260223_0017`

## Carry-Forward Follow-Ups (Week 16+)
| ID | Severity | Description |
|---|---|---|
| F58 | Low | `uploaded_files.user_id` index remains deferred. |
| F62 | Low | File-read path compile behavior remains accepted for current throughput. |
| F64 | Low | Worker DB URL precedence remains explicit deployment policy. |
| F70 | Medium | Staging deploy drift still blocks Week 14/15 agent-route validation (`/api/v1/agents*` returns `404`). |

## Week 16 Entry Gates
1. Redeploy staging with Week 15 API build and re-run `W15-07` F70 closure legs.
2. Confirm OpenRouter function-calling support matrix per model alias and fallback behavior.
3. Validate scratchpad cutoff (`AGENT_PRIVATE_CONTEXT_TURNS_KEEP=3`) against observed latency/quality.
4. Keep F41 transaction policy locked on all turn write paths.
