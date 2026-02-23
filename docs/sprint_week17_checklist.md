# Pantheon MVP - Sprint Week 17 Checklist

Sprint window: Week 17 (Cycle 6 Part 1 - SSE Streaming)  
Owner: Codex  
Reviewer: External supervising engineer  
Last updated: 2026-02-23

## Sprint Goal
Introduce SSE token streaming for turn execution, with credit enforcement preflight and single-commit persistence at stream close.

## Baseline
- Local tests at sprint open: `163` passing.
- Migration head at sprint open: `20260223_0018`.

## Definition of Done
- `LlmGateway` supports streaming via `stream()` without changing existing `generate()` behavior.
- New `POST /sessions/{session_id}/turns/stream` endpoint emits SSE `chunk` and `done` events.
- Streaming endpoint rejects tool-enabled execution with `422`.
- Streaming endpoint enforces credit check preflight (`402` when enabled and depleted).
- Usage + wallet debit are staged and committed once at stream close.
- Week 17 tests added and all tests pass.

## Week 17 Task Checklist
| ID | Task | Status | Acceptance Criteria | Evidence / Notes |
|---|---|---|---|---|
| W17-01 | Gateway streaming protocol | DONE | `LlmGateway.stream()` available; OpenRouter implementation yields deltas and resolves final usage metadata | Implemented in `apps/api/app/services/llm/gateway.py` with `StreamingContext` (`chunks`, `usage_future`, `provider_model_future`). |
| W17-02 | Streaming turn endpoint | DONE | New `/sessions/{session_id}/turns/stream` SSE endpoint; no-cache headers; tools-enabled returns 422 | Implemented in `apps/api/app/api/v1/routes/sessions.py`, emits `chunk` and `done` SSE events with `text/event-stream`. |
| W17-03 | Usage/persistence at stream close | DONE | Usage, llm events, wallet debit, turn/messages persisted and committed once after stream exhaustion | Implemented in stream close path in `apps/api/app/api/v1/routes/sessions.py`; same recorder/debit path as non-stream endpoint. |
| W17-04 | Tests | DONE | 4 required tests for chunks, persistence, tools rejection, and credit enforcement | Added in `tests/test_sessions_routes.py` and passing. |

## Verification
- Full suite: `167/167` passing.
- Ruff critical (`E9,F63,F7,F82`): passing.
- Local migration head unchanged: `20260223_0018`.

## Carry-Forward At Week 17 Close
| ID | Severity | Description |
|---|---|---|
| F58 | Low | `uploaded_files.user_id` index deferred. |
| F62 | Low | `file_read` compile-per-turn behavior accepted at current throughput. |
| F64 | Low | Worker DB URL precedence remains explicit deployment policy. |
| F70 | Medium | Staging deploy drift still present; Week 14+ API/migrations not active on staging deployment. |

