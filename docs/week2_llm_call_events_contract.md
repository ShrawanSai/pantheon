# Week 2 Contract: `llm_call_events` Schema

Date: 2026-02-21  
Status: Approved-for-migration contract (input to W2-04)

## Purpose
Define the exact schema contract for `llm_call_events` before writing Alembic migration SQL.

This contract aligns with:
- SRS `FR-BILL-001` and `FR-BILL-002`
- Week 2 gate requiring usage ledger migration before metering-integrated feature work

## Table Design Goals
- Append-only usage ledger (no mutable business state).
- Per-call auditability for billing and admin analytics.
- Preserve financial records even if chat entities are later purged.

## Column Contract (W2-04 Migration)

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | `String(36)` | No | Primary key UUID string (app-generated). Avoids DB extension dependency for MVP migrations. |
| `user_id` | `String(64)` | No | FK -> `users.id` (billing subject). |
| `room_id` | `String(64)` | Yes | FK -> `rooms.id`; nullable for direct-chat calls. |
| `direct_session_id` | `String(64)` | Yes | Direct-chat session identifier, app-generated UUID string (`dcs_*` or UUID format), no FK in W2 because no `direct_sessions` table exists yet. |
| `session_id` | `String(64)` | Yes | FK -> `sessions.id`; primary conversational context. |
| `turn_id` | `String(64)` | Yes | FK -> `turns.id`; event source turn. |
| `step_id` | `String(64)` | Yes | FK -> `turn_steps.id`; step-level attribution. |
| `agent_id` | `String(64)` | Yes | Agent identifier snapshot for analytics joins; no FK (see FK strategy). |
| `provider` | `String(32)` | No | Provider name (MVP default: `openrouter`). |
| `model_alias` | `String(32)` | No | Pantheon alias (`llama`,`qwen`,`deepseek`,`gpt_oss`,`premium`). |
| `provider_model` | `String(128)` | No | Exact model string sent to provider (audit). |
| `input_tokens_fresh` | `Integer` | No | Fresh input tokens billed at full weight. |
| `input_tokens_cached` | `Integer` | No | Cached input tokens billed at cached weight. |
| `output_tokens` | `Integer` | No | Output tokens. |
| `total_tokens` | `Integer` | No | Stored total from provider payload where available. |
| `oe_tokens_computed` | `Numeric(20,4)` | No | Computed OE tokens using pricing formula. |
| `provider_cost_usd` | `Numeric(20,8)` | No | Provider-side cost snapshot in USD. |
| `credits_burned` | `Numeric(20,4)` | No | Credits debited for this call. |
| `latency_ms` | `Integer` | Yes | End-to-end call latency. |
| `status` | `String(24)` | No | Call outcome (`success`,`error`,`timeout`,`rate_limited`, etc). |
| `pricing_version` | `String(32)` | No | Pricing version used at debit time (e.g. `v1`). |
| `request_id` | `String(128)` | Yes | Provider/request correlation ID for traceability. |
| `created_at` | `DateTime(timezone=True)` | No | Server default `now()`; immutable event timestamp. |

## Required Fallback Rule (Cached Tokens)
If provider response does not include cached token data:
- set `input_tokens_cached = 0`
- treat all input tokens as fresh:
  - `input_tokens_fresh = prompt/input token count`

This is mandatory for migration-time contract correctness.

## Session Attribution Rule
Exactly one conversational attribution path must be used per event:
- Room flow call:
  - `session_id` is set (FK -> `sessions.id`)
  - `direct_session_id` is `NULL`
- Direct chat call:
  - `direct_session_id` is set (app-generated)
  - `session_id` is `NULL`

W2 migration will not add a DB check constraint yet; this rule is enforced by write-path logic and tests.

## OE Formula (stored in `oe_tokens_computed`)
`OE = (input_tokens_fresh * 0.35) + (input_tokens_cached * 0.10) + output_tokens`

## Credits Formula (stored in `credits_burned`)
`credits_burned = oe_tokens_computed / 10_000`

This matches pricing rule: `1 credit = 10,000 OE tokens`.

Rounding/storage:
- store as `Numeric(20,4)` in DB.

## FK Strategy Decisions
1. `user_id` FK -> `users.id` with `ON DELETE RESTRICT`.
- Ledger should never lose billing subject linkage.

2. Context FKs (`room_id`, `session_id`, `turn_id`, `step_id`) use `ON DELETE SET NULL`.
- Preserve usage ledger even if conversational artifacts are purged/retained differently.

3. `agent_id` is intentionally non-FK in W2.
- Agent records can change across room snapshots/direct sessions.
- Store as immutable identifier snapshot for analytics consistency.

## Index Strategy (W2-04 Migration)
- `idx_llm_call_events_user_created_at` on (`user_id`, `created_at`)
- `idx_llm_call_events_session_created_at` on (`session_id`, `created_at`)
- `idx_llm_call_events_turn_id` on (`turn_id`)
- `idx_llm_call_events_model_alias_created_at` on (`model_alias`, `created_at`)
- `idx_llm_call_events_created_at` on (`created_at`)
- `uq_llm_call_events_request_id` partial unique index on `request_id` where `request_id IS NOT NULL`
  - SQLAlchemy/Alembic form:
  - `sa.Index("uq_llm_call_events_request_id", "request_id", unique=True, postgresql_where=sa.text("request_id IS NOT NULL"))`

## Non-Goals for W2-04
- No aggregation/materialized rollup table yet.
- No Stripe ledger coupling yet.
- No backfill process in this migration; only forward-write contract.
