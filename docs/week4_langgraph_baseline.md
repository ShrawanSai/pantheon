# Pantheon Week 4 - LangGraph Baseline (W4-03)

Date: 2026-02-21  
Owner: Codex

## Goal
Run the existing single-turn execution path through LangGraph while preserving current API behavior and DB writes.

## Graph Scope (Baseline)
- One graph invocation per turn request.
- Single node execution (`call_model`) in Week 4 baseline.
- Checkpointer:
  - preferred: Postgres checkpointer (`langgraph.checkpoint.postgres.PostgresSaver`) using `DATABASE_POOL_URL`
  - fallback: in-memory (`MemorySaver`) when Postgres checkpointer package/runtime is unavailable

## State Contract
`TurnExecutionState` fields:
- `model_alias: str`
- `messages: list[GatewayMessage]`
- `max_output_tokens: int`
- `provider_model: str`
- `text: str`
- `usage_input_tokens_fresh: int`
- `usage_input_tokens_cached: int`
- `usage_output_tokens: int`
- `usage_total_tokens: int`

## Node Contract
`call_model(state)`:
- Input: `model_alias`, `messages`, `max_output_tokens`
- Calls LLM gateway with normalized `GatewayRequest`
- Returns:
  - `provider_model`
  - `text`
  - all usage token fields

## Integration Point
- `apps/api/app/services/orchestration/mode_executor.py`
  - `LangGraphModeExecutor.run_turn(...)` performs `graph.ainvoke(...)`
- `apps/api/app/api/v1/routes/sessions.py`
  - `POST /api/v1/sessions/{session_id}/turns` now uses `LangGraphModeExecutor` for model execution
  - DB writes (turn/messages/summary/audit/usage) remain in route service flow for Week 4 baseline

## Manual Mode Scope (W4-04)
- Manual/tag mode is intentionally single-agent-per-turn for MVP.
- When multiple valid tags are present (e.g., `@writer @researcher`), only the first valid tagged agent in message order is dispatched.
- Multi-tag fan-out is deferred and tracked in Week 4 follow-up `F44`.

## Non-Goals (Deferred)
- Multi-node mode orchestration graph
- Human-in-the-loop interrupts
- Tool subgraphs
- Orchestrator-mode structured routing (tracked in F22)
