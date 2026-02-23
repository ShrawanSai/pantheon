# Sprint Week 17 Handoff

## Sprint Goal
Deliver SSE token streaming for turn execution with enforcement preflight and single-transaction persistence at stream close.

## Completion Snapshot
- Tasks completed: `W17-01` through `W17-04`.
- Local tests at close: `167/167` passing.
- Ruff critical checks (`E9,F63,F7,F82`): passing.
- Local migration head: `20260223_0018` (no new migration in Week 17).

## Delivered Artifacts
- W17-01 (gateway streaming protocol):
  - Updated `LlmGateway` protocol with `stream()`
  - Added `StreamingContext` dataclass
  - Implemented OpenRouter streaming in `apps/api/app/services/llm/gateway.py`

- W17-02 (streaming endpoint):
  - Added `POST /sessions/{session_id}/turns/stream` in `apps/api/app/api/v1/routes/sessions.py`
  - SSE output format:
    - `{"type":"chunk","delta":"..."}`
    - `{"type":"done","turn_id":"...","provider_model":"..."}`
  - Response headers include `Cache-Control: no-cache` and `X-Accel-Buffering: no`
  - Tool-enabled streaming returns `422` with `{"detail":"streaming not supported when tools are enabled"}`

- W17-03 (usage + persistence at stream close):
  - Stream close path now stages:
    - `Turn`
    - `Message` rows
    - usage via `UsageRecorder.stage_llm_usage(...)`
    - wallet debit via `WalletService.stage_debit(...)`
  - Single `db.commit()` at close preserves F41 policy

- W17-04 (tests):
  - Added to `tests/test_sessions_routes.py`:
    - `test_streaming_endpoint_yields_chunks`
    - `test_streaming_endpoint_persists_turn`
    - `test_streaming_rejects_when_tools_enabled`
    - `test_streaming_enforces_credit_check`

## Runtime Capability At Close
Compared with Week 16 close:
- clients can now request streamed turn output over SSE
- streamed turns still preserve billing + persistence invariants
- enforcement preflight applies consistently to both sync and stream turn paths

## Migration Chain At Close
`20260221_0001 -> 20260221_0002 -> 20260221_0003 -> 20260221_0004 -> 20260221_0005 -> 20260222_0006 -> 20260222_0007 -> 20260222_0008 -> 20260222_0009 -> 20260222_0010 -> 20260222_0011 -> 20260222_0012 -> 20260223_0013 -> 20260223_0014 -> 20260223_0015 -> 20260223_0016 -> 20260223_0017 -> 20260223_0018`

## Carry-Forward Follow-Ups
| ID | Severity | Description |
|---|---|---|
| F58 | Low | `uploaded_files.user_id` index deferred. |
| F62 | Low | `file_read` compile-per-turn behavior accepted at current throughput. |
| F64 | Low | Worker DB URL precedence remains explicit deployment policy. |
| F70 | Medium | Staging deploy drift: Week 14+ API/migrations not active on deployed staging instance. |

## Week 18 Entry Gates
1. Add Stripe config via env only (`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`), never hardcode.
2. Top-up credits must be grant-on-webhook-success only; no grant on PaymentIntent creation.
3. Keep F41 single-commit policy on all new write paths (webhook grant path included per request).
4. Keep enforcement thresholds in `docs/enforcement_production_criteria.md` unresolved until product owner input.

