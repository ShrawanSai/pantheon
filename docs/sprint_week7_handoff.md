# Pantheon MVP - Sprint Week 7 Handoff

Date: 2026-02-22  
Owner: Codex  
Reviewer: External supervising engineer

## Sprint Summary
Week 7 is closed with `W7-01` through `W7-07` completed.  
Final validation snapshot: `66/66` tests passing and Ruff critical rules (`E9,F63,F7,F82`) passing.

## Completion Snapshot
- Sprint status: Closed
- Test count at close: `66/66` passing
- Ruff critical checks: passing
- Staging migration head at close: `20260222_0007`
- Staging runtime evidence (consolidated):
  - Health: `GET /api/v1/health -> 200`
  - Auth: `GET /api/v1/auth/me -> 200`
  - Deny path (no tool permission): completed turn with zero `tool_call_events`
  - Allow path (search permission): completed turn with one `tool_call_events` success row and non-null `latency_ms`
  - No 5xx observed across the consolidated validation sequence

## Artifacts Shipped
### Core application and services
- `apps/api/app/services/tools/permissions.py`
- `apps/api/app/services/tools/search_tool.py`
- `apps/api/app/services/tools/file_tool.py`
- `apps/api/app/services/orchestration/mode_executor.py`
- `apps/api/app/api/v1/routes/sessions.py`
- `apps/api/app/db/models.py`
- `apps/api/app/core/config.py`

### Migrations
- `infra/alembic/versions/20260222_0007_create_tool_call_events.py`

### Sprint tracking/documentation
- `docs/sprint_week7_checklist.md`

### Test files (8)
- `tests/test_sessions_routes.py`
- `tests/test_rooms_routes.py`
- `tests/test_langgraph_mode_executor.py`
- `tests/test_tool_permissions.py`
- `tests/test_orchestrator_manager.py`
- `tests/test_summary_extractor.py`
- `tests/test_summary_generator.py`
- `tests/test_api_scaffold.py`

## Migration Chain
Current staging head confirms chain `0001 -> 0007`.
- Current head: `20260222_0007`
- New Week 7 migration: `20260222_0007_create_tool_call_events.py`

## Runtime Capability At Close
Compared to Week 6 close, the system now additionally supports:
- Tool permission parsing and enforcement primitives (`tool_permissions_json` source of truth).
- Tavily-backed search tool integration through LangGraph execution path.
- Compile-time tool-node gating per agent permission set in `mode_executor`.
- Tool telemetry persistence (`tool_call_events`) staged before single route commit (F41 transaction policy preserved).
- Verified staging deny/allow behavior for tool usage on the same deployment.

## Carry-Forward To Week 8+
| ID | Severity | Description |
|---|---|---|
| F53 | Low | Search trigger is heuristic (`search:` / `search for`) and not autonomous/function-calling tool dispatch. |
| F54 | Low | Tavily API key is sent in request JSON body; evaluate Authorization header hardening. |
| F55 | Low | Migration `20260222_0007` lacks DB `server_default` for `tool_call_events.status` while ORM defines one. |
| F56 | Low | `ToolCallEvent.user_id` currently has no FK; confirm and document intent. |
| F57 | Low | `ToolCallEvent.room_id` uses `String(36)` while broader project convention is often `String(64)`. |
| F51 | Deferred | `SummaryGenerationResult.used_fallback` is still not emitted into route-level observability. |

## Week 8 Entry Gates
1. Confirm Week 7 closure artifacts are approved (`docs/sprint_week7_checklist.md` and this handoff).
2. Lock Week 8 file-tools scope explicitly (TXT/MD/CSV first vs full PDF/DOCX set in Week 8).
3. Confirm arq worker responsibilities and queue routing for file parse jobs before coding.
4. Decide tool telemetry extension policy for file tools (`tool_call_events` schema reuse vs additive fields).
5. Confirm staging env parity for file-processing dependencies before runtime rollout.

## Recommended Week 8 Build Order
1. Finalize Week 8 file tool scope and acceptance matrix (formats, size limits, failure behavior).
2. Implement file tool service surface and permission-gated execution path.
3. Add arq job pipeline for file parsing and asynchronous processing.
4. Persist file tool telemetry into existing `tool_call_events` model.
5. Run staging deny/allow + parse-success/failure validation.
6. Publish Week 8 handoff with migration/runtime evidence.
