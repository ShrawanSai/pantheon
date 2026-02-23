# Pantheon MVP Master Plan

## Summary
This document captures the full MVP plan discussed: product scope, architecture, stack, interaction modes, LangGraph orchestration behavior, memory model, token/cost tracking, and admin panel requirements.

## Product Scope
- Audience: solo professionals.
- Launch model: free beta with usage caps, with paid tiers configured and ready to enable.
- Platform: web-first.
- Core room concept: persistent Council Rooms with purpose and configurable agents.
- Core backend interaction modes: `manual`, `roundtable`, `orchestrator`.
- UI presets (not separate backend modes): `chat`, `docreview`, `webresearch`, `editing`.
- Hard requirement: per-user, per-LLM token and cost tracking for internal admin/finance.

## Tech Stack (Python-first)
- Frontend: Next.js + TypeScript.
- Backend API: FastAPI + Pydantic v2 + SQLAlchemy + Alembic.
- Orchestration: LangGraph.
- Workers/queues: Celery + Redis.
- Primary database: PostgreSQL.
- Vector memory: pgvector (in PostgreSQL).
- File storage: S3 or R2.
- LLM gateway: unified server-side adapter layer (LiteLLM-style).
- Observability: Sentry + OpenTelemetry.
- Product analytics: PostHog.

## LLM Access Architecture
- All LLM calls are server-side only (never directly from browser).
- One gateway path for all providers/models.
- Every LLM call writes one append-only usage event.
- Stored fields per call include:
  - user_id, room_id, session_id, turn_id, agent_id
  - provider, model
  - prompt_tokens, completion_tokens, cached_tokens, total_tokens
  - credits_burned
  - provider_cost_usd
  - internal_overhead_usd
  - internal_total_cost_usd
  - latency_ms, status, request_id, pricing_version, timestamp
- Daily/monthly rollups are derived for admin reporting and reconciliation.

## Rooms and Memory Storage
- Short-term memory: recent session messages.
- Durable execution state: LangGraph checkpoints in Postgres.
- Canonical transcript memory: `messages` table.
- Mid-session compression: `session_summaries` checkpoints.
- Long-term memory: vectorized `memory_items` and `document_chunks` in pgvector.
- File payloads: object storage, with chunk metadata persisted in Postgres.
- Redis is transient runtime/cache only, not source of truth.

## Agent Communication
Agents do not communicate peer-to-peer directly.
Communication is state-mediated via shared LangGraph state (blackboard pattern):
- Manager/specialists read shared state.
- Specialist outputs are written back to state.
- Subsequent specialists/manager read updated state.
- This is auditable, replayable, and cost-trackable.

## Interaction Modes

### 1) Manual Mode
- User must explicitly tag target agents.
- Only tagged agents respond.
- Response order follows tag order.
- If no valid tags are present, return validation error (no fallback).
- Responding agents use shared conversation context.

### 2) Round Table Mode
- All agents respond each turn.
- Strict sequential order by room config.
- Later agents see earlier same-turn outputs.
- If one agent fails, continue others and mark turn as partial.

### 3) Orchestrator Mode
- Manager acts as dynamic router (not fixed workflow).
- Manager may select any subset of specialists.
- Manager may invoke the same specialist multiple times.
- Max depth per agent per user turn: 3.
- Max total specialist invocations per user turn: 12.
- Specialists can use tools; manager cannot.
- User sees all intermediate specialist outputs.
- Manager produces final synthesis summary.
- Failure policy: continue with partial results and annotate failures.
- Manager model selection: auto-selected by default, user-configurable in room settings.

## LangGraph Execution Model
- One graph run per user turn (resumable).
- Postgres checkpointer enabled.
- No HITL approvals in MVP UI.
- Design keeps interrupt hooks for future HITL expansion.

## Credits and Cost Model
- 1 credit = 10,000 OE tokens.
- OE formula: fresh * 0.35 + cached * 0.10 + output * 1.0.
- Tool credits: first 2 calls/session free, then per-tool mapping.
- Base credits per request: `OE / 10,000`.
- Billed model multiplier rule: `max(model_multiplier, 0.5)`.
- Overage and metered billing rate: `$0.03` per credit.
- Minimum charge policy: no model can bill below `0.5x`.
- Pricing versioning is required so historical costs are reproducible.
- Model multipliers (pricing version `2026-02-20`):
  - DeepSeek V3.x: `1.00x`
  - Llama 4 Scout: `0.50x` (floor applied)
  - Qwen3-235B: `0.50x` (floor applied)
  - GPT-OSS-120B: `0.50x` (floor applied)
  - Kimi K2.x: `2.40x`
  - GLM-4.5/4.7 class: `2.55x`
  - GPT-5-mini: `2.25x`
  - GPT-4.1: `10.00x`
  - GPT-4o: `12.50x`
  - GPT-5 / GPT-5.1: `11.25x`
  - GPT-5.2: `15.75x`
  - Gemini Pro class: `14.00x`
  - Claude Sonnet class: `18.00x`
  - Grok class: `18.00x`
  - Claude Opus class: `30.00x`
- Internal cost basis for admin: provider + overhead.

## Pricing Strategy (Paid Plan Ready)
- Plan tiers:
  - Starter: `$29/month`, `495` included credits.
  - Pro: `$79/month`, `1,980` included credits.
  - Power: `$149/month`, `4,180` included credits.
- Overage: `$0.03` per additional credit.
- Metering method:
  - Compute OE tokens from input/cached/output.
  - Convert to base credits (`OE / 10,000`).
  - Apply billed multiplier with `0.5x` minimum.
  - Add post-free tool credits.
- Margin policy:
  - Keep model pricing near a consistent gross margin target by using model-true multipliers.
  - Reprice using `pricing_version` when provider rates change.
- Admin reporting requirements:
  - Revenue, provider cost, overhead, and gross margin by user, model, room, and plan tier.

## Admin Panel (MVP Required)
Admin panel is required in MVP, inside FastAPI stack at `/admin`.

### Auth/Security
- Separate admin auth system (not customer auth).
- Superuser accounts.
- Bcrypt password hashes.
- Secure admin session.
- Admin audit logs for all control actions.

### Analytics (Read)
- Per-user per-LLM token usage.
- Per-user per-LLM provider cost and internal cost.
- Cost split: provider vs overhead.
- Revenue and gross margin by model and tier.
- Sessions/day, avg credits/session, mode distribution.
- Top users/models/providers by tokens and cost.

### Active User Base Metrics
- Session-based DAU, WAU, MAU.
- DAU/MAU stickiness.
- New vs returning active users.
- Default trend window: last 30 days.

### Controls (Write)
- Set user monthly caps.
- Suspend/reactivate users.
- Enable/disable model access policies.
- CSV export for finance/ops.

## API and Internal Interfaces
- `POST /rooms/{room_id}/messages`
- `GET /sessions/{session_id}/stream`
- `GET /sessions/{session_id}/turns/{turn_id}`
- `GET /admin/analytics/usage`
- `GET /admin/analytics/active-users`
- `POST /admin/users/{user_id}/caps`
- `POST /admin/users/{user_id}/suspend`
- `POST /admin/model-access/rules`

Internal service interfaces:
- `ModeExecutor.execute_turn(mode, context, user_input, options)`
- `ManagerRouter.next_action(state)`
- `LLMGateway.invoke(call_spec)`
- `UsageRecorder.record_call(event)`

## Core Data Model
- users
- rooms
- agents
- sessions
- turns
- turn_steps
- messages
- session_summaries
- memory_items
- document_chunks
- llm_call_events (append-only source of truth)
- daily_usage_rollups
- daily_active_user_rollups
- admin_users
- admin_audit_logs

## Implementation Phases
1. Foundation and schema setup.
2. LLM gateway + usage ledger + pricing versioning.
3. LangGraph state/checkpoint integration.
4. Manual mode.
5. Round Table mode.
6. Orchestrator mode (routing, caps, synthesis).
7. Memory retrieval + summarization + guardrails.
8. Admin panel analytics + controls.
9. Stability and beta hardening.

## Test Scenarios
- Manual mode: explicit tags required and enforced.
- Round Table: strict ordered responses and same-turn context visibility.
- Orchestrator: subset routing, repeated agents allowed, depth and global caps enforced.
- Specialist-only tool use in orchestrator enforced.
- Partial-failure continuation works.
- Every LLM call creates exactly one usage event.
- Rollup reconciliation against raw events.
- Active user metrics match session-based definition.
- Guardrails trigger deterministically.
- Streaming event ordering and replay on reconnect.
- Admin control actions permissioned and audited.

## Defaults and Assumptions
- Web-first MVP only.
- Free beta with caps remains supported; paid tiers can be activated without architecture changes.
- LangGraph included in MVP now.
- Orchestrator is transparent (shows intermediate steps + final synthesis).
- Admin panel is internal ops-focused, not tenant-admin.
