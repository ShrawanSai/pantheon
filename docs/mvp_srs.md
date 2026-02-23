# Pantheon MVP Software Requirements Specification (SRS)

Version: 1.1  
Date: 2026-02-20  
Status: Draft for implementation

## 1. Purpose
Define a decision-complete MVP specification for Pantheon, a multi-agent AI application with room-based collaboration, direct agent chat, usage-based credits, and internal admin analytics.

This SRS reflects all product and technical decisions made so far and is intended for implementation by a professional software team.

## 2. Scope
Pantheon MVP will deliver:
- A web-first, mobile-friendly application with a familiar chat-first UX.
- Room-based multi-agent workflows using three interaction modes:
1. `manual/tag`
2. `roundtable`
3. `orchestrator`
- Direct chat with a single agent (outside room workflows).
- Tooling for:
1. Web search
2. File upload and file-reading/parsing
- Per-user, per-model token and cost tracking for internal operations.
- Subscription credits and top-ups.
- Internal admin panel with usage, cost, and active-user metrics.

Out of scope for MVP:
- Multi-user collaborative rooms.
- Browser automation tools.
- Code execution tools.
- Native mobile apps.
- Enterprise SSO and granular enterprise RBAC.

## 3. Product Context
Pantheon is a chat-centric product where users configure agents (model + role + tool access), run workflows in rooms, and see transparent multi-step outputs with usage/cost tracking.

MVP target:
- Closed beta.
- Up to 1k MAU in first 3 months.
- Canada-first hosting posture.

## 4. Users and Roles
1. End User
- Creates rooms.
- Configures agents and tools.
- Runs chats in selected mode.
- Uses direct agent chat.
- Uploads files and consumes outputs.
- Views own usage and billing.

2. Admin Owner
- Full admin dashboard access.
- Can change orchestrator manager default model.
- Can apply user controls (caps, suspension, model access policies).
- Can audit billing/usage/cost.

3. Admin Analyst
- Read-only analytics access.
- No mutation permissions.

## 5. System Architecture
## 5.1 Frontend
- Next.js (TypeScript) on Vercel.
- ChatGPT/Slack hybrid layout.
- Responsive web first (mobile browser optimized).
- NDJSON/SSE client for streaming step events (WebSocket deferred post-MVP).

## 5.2 Backend API
- FastAPI (Python) on Railway.
- LangGraph-based orchestration runtime.
- REST + streaming endpoints (NDJSON/SSE first).

## 5.3 Background Jobs
- arq (Redis-backed) queue + separate worker service on Railway.
- Jobs for file parsing, retries, retention purge, and rollups.

## 5.4 Data and Storage
- Supabase Postgres (primary system of record).
- Supabase Storage (uploaded files).
- Redis (queue/transient runtime state only).
- Alembic is the required migration strategy for Python services.

## 5.5 External Integrations
- OpenRouter (all LLM access in MVP).
- Tavily (search tool).
- Stripe (subscriptions + top-ups, introduced in Cycle 6).
- Sentry (error monitoring).

## 6. Functional Requirements
## 6.1 Authentication and Session
FR-AUTH-001  
System shall support magic-link authentication using Supabase Auth.

FR-AUTH-002  
Unauthenticated users shall not access room, chat, billing, or admin APIs.

FR-AUTH-003  
Admin panel routes shall enforce role checks (`owner`, `analyst`).

## 6.2 Room Management
FR-ROOM-001  
User shall create, list, read, update, and soft-delete rooms.

FR-ROOM-002  
Each room shall be owned by one user (single-user room model in MVP).

FR-ROOM-003  
Each room shall persist current mode and pending mode.

FR-ROOM-004  
Setting room mode shall update `pending_mode` only.

FR-ROOM-005  
Pending mode shall become effective only at next send request.

FR-ROOM-006  
Mode changes during an active turn shall not affect in-flight execution.

## 6.3 Agent Management
FR-AGENT-001  
User shall add, edit, reorder, and remove agents in a room.

FR-AGENT-002  
Each agent shall include:
1. `id`
2. `name`
3. `model_alias`
4. `role_prompt`
5. `tool_permissions`

FR-AGENT-003  
Supported MVP model aliases:
1. `llama`
2. `qwen`
3. `deepseek`
4. `gpt_oss`
5. `premium` (Gemini Pro class)

FR-AGENT-004  
At turn start, system shall snapshot room roster. Execution uses snapshot consistently for that turn.

FR-AGENT-005  
Agent add/remove/update shall affect the next send request without requiring room reload.

FR-AGENT-006  
Agents shall be aware of room roster context, but worker responses must remain user-task-focused and must not devolve into agent-to-agent handoff chatter.

## 6.4 Conversation Modes
FR-MODE-001 Manual/Tag  
Only explicitly tagged agents shall run. No fallback if no valid tags.

FR-MODE-002 Roundtable  
All active room agents shall run in configured sequence.

FR-MODE-003 Orchestrator  
Manager model routes which worker agents run and in what order, then produces final synthesis.

FR-MODE-004  
Default orchestrator manager shall be `deepseek`; admin can override globally.

FR-MODE-005  
Each step output shall be rendered as separate timeline messages, not a merged blob.

FR-MODE-006  
Roundtable must stream responses as each agent finishes; do not wait for all agents before display.

## 6.5 Direct Agent Chat
FR-DIRECT-001  
System shall support direct chat with one selected agent outside room mode workflows.

FR-DIRECT-002  
Direct chat memory shall be separate from room memory.

FR-DIRECT-003  
Direct chat shall enforce same tool permissions and billing rules as room chat.

## 6.6 Tooling: Search and Files
FR-TOOL-001  
Only two tools are in MVP:
1. Web search
2. File upload/read

FR-TOOL-002  
Search tool provider shall be Tavily.

FR-TOOL-003  
File type support in MVP:
1. PDF
2. DOCX
3. TXT
4. MD
5. CSV

FR-TOOL-004  
Upload limits:
1. 10MB maximum per file
2. 100MB maximum total per room

FR-TOOL-005  
Tool invocation shall be enforced server-side by per-agent tool permissions.

FR-TOOL-006  
File access rules by mode:
1. Orchestrator: manager may direct eligible worker to read files.
2. Roundtable: only agents with file permission may read files.
3. Manual/tag: tagged agent must have file permission to read files.

FR-TOOL-007  
Tool and file usage shall be recorded per step for analytics and billing transparency.

## 6.7 Streaming and Real-Time UX
FR-RT-001  
Streaming transport shall be NDJSON/SSE-first for step-level events.

FR-RT-002  
Client shall show in-progress loader while responses are being generated.

FR-RT-003  
System shall emit structured events:
1. `turn_started`
2. `step_started`
3. `step_delta` (optional token chunks)
4. `step_completed`
5. `turn_completed`
6. `turn_failed`

FR-RT-004  
On reconnect/interruption, client can fetch turn status and restore timeline consistency.

## 6.8 Usage Metering and Billing
FR-BILL-001  
Each LLM call must produce one append-only usage record (`llm_call_event`).

FR-BILL-002  
Usage event fields shall include:
1. `user_id`
2. `room_id` or `direct_session_id`
3. `turn_id`
4. `step_id`
5. `agent_id`
6. `provider`
7. `model`
8. `prompt_tokens`
9. `completion_tokens`
10. `cached_tokens`
11. `total_tokens`
12. `provider_cost_usd`
13. `credits_burned`
14. `latency_ms`
15. `status`
16. `pricing_version`
17. `request_id`

FR-BILL-003  
Credit formula shall match current pricing model:
1. `1 credit = 10,000 OE tokens`
2. `OE = (fresh * 0.35) + (cached * 0.10) + output`
3. billed multiplier floor = `0.5x`
4. tool credit rules per pricing version

FR-BILL-004  
System shall support:
1. monthly included plan credits
2. paid top-up credits via Stripe

FR-BILL-005  
Subscriptions and top-ups must be idempotent and webhook-safe.

FR-BILL-006  
If provider response does not return `cached_tokens`, system shall set `cached_tokens = 0` and treat all input tokens as fresh for billing, with this policy documented in pricing version metadata.

## 6.9 Pricing and Plans
FR-PLAN-001  
MVP supports tier-based allowlists for model access.

FR-PLAN-002  
Current plan basis (from pricing strategy):
1. Starter: 495 credits/month
2. Pro: 1,980 credits/month
3. Power: 4,180 credits/month

FR-PLAN-003  
Overage or top-up credit burn shall use the same credit accounting engine.

## 6.10 Admin Panel
FR-ADMIN-001  
Admin panel shall be integrated within main web app under protected routes.

FR-ADMIN-002  
Admin analytics shall include:
1. per-user per-model token usage
2. per-user per-model cost
3. provider cost vs internal cost
4. active users (DAU/WAU/MAU)
5. top users/models by cost and tokens

FR-ADMIN-003  
Admin controls shall include:
1. user cap updates
2. suspend/reactivate users
3. model access policy changes
4. orchestrator manager model setting

FR-ADMIN-004  
All admin write actions shall be audit-logged.

## 6.11 Data Lifecycle and Retention
FR-DATA-001  
Default retention target is 90 days for chat/file data.

FR-DATA-002  
Delete behavior:
1. soft delete immediately
2. restore allowed for 7 days
3. hard purge after grace period

FR-DATA-003  
Retention jobs must run asynchronously and be observable.

## 7. External Interface Requirements
## 7.1 UI Requirements
UI-001  
App shall provide a familiar chat-first UX (ChatGPT/Slack hybrid).

UI-002  
Core screens:
1. home/dashboard
2. room create/edit
3. room workspace
4. direct agent chat
5. billing and usage
6. admin dashboard

UI-003  
Mobile responsive behavior is required for core flows.

UI-004  
Mode change UI must clearly indicate "applies on next send".

UI-005  
Turn timeline shall display each agent message separately, with model/mode labels.

## 7.2 API Requirements (MVP)
Required endpoint families:
1. auth
2. rooms
3. agents
4. mode switching
5. turns/messages
6. direct chat sessions
7. files and tool usage
8. billing and top-ups
9. admin analytics and controls
10. streaming endpoints

## 8. Non-Functional Requirements
## 8.1 Performance
NFR-PERF-001  
Non-LLM API endpoints should target p95 < 500ms under MVP load.

NFR-PERF-002  
First streamed step should target p95 < 8 seconds for non-file prompts.

NFR-PERF-003  
System should support beta scale up to 1k MAU with graceful degradation controls.

## 8.2 Reliability
NFR-REL-001  
Service availability target: 99.5% monthly for MVP.

NFR-REL-002  
Turn execution must handle partial failures and surface failure metadata to user/admin.

NFR-REL-003  
Retry policy and timeout policy required for LLM and tool calls.

## 8.3 Security
NFR-SEC-001  
All traffic over HTTPS/TLS.

NFR-SEC-002  
No provider API keys exposed client-side.

NFR-SEC-003  
Signed upload access, server-side MIME/type checks, and size validation required.

NFR-SEC-004  
Role-based access enforcement for admin routes and actions.

NFR-SEC-005  
Structured audit logging required for security-sensitive operations.

## 8.4 Observability
NFR-OBS-001  
Sentry integration required for backend/frontend exceptions.

NFR-OBS-002  
Structured logs with request/turn correlation IDs required.

NFR-OBS-003  
Basic metrics for request rates, failure rates, latency, queue depth, and job failures required.

## 8.5 Accessibility and Usability
NFR-UX-001  
Core flows must meet standard accessible behavior:
1. keyboard navigability
2. clear labels/errors
3. meaningful focus states
4. readable contrast

NFR-UX-002  
English-only UI/content for MVP.

## 9. Data Model (MVP Logical Tables)
Core:
1. `users`
2. `rooms`
3. `room_agents`
4. `room_sessions`
5. `turns`
6. `turn_steps`
7. `messages`
8. `direct_sessions`

Tools/files:
1. `files`
2. `file_parsing_jobs`
3. `file_access_events`
4. `tool_call_events`

Billing:
1. `plans`
2. `subscriptions`
3. `credit_wallets`
4. `credit_transactions`
5. `pricing_versions`
6. `model_pricing`
7. `llm_call_events`
8. `usage_rollups_daily`
9. `usage_rollups_monthly`

Admin/security:
1. `admin_users`
2. `admin_roles`
3. `admin_audit_logs`

## 10. Acceptance Test Matrix
AT-001  
Mode switch applies on next send only.

AT-002  
Agent add/remove updates execution roster on next send.

AT-003  
Manual mode rejects send when no valid tags.

AT-004  
Roundtable streams each agent step independently and visibly.

AT-005  
Orchestrator emits worker steps plus final synthesis.

AT-006  
Tool permissions enforced server-side (search/file denied where unauthorized).

AT-007  
Unsupported file type or over-limit upload returns clear validation error.

AT-008  
Each LLM call creates exactly one usage event row.

AT-009  
Credit burn equals formula output for reference test prompts.

AT-010  
Stripe webhook idempotency prevents duplicate credit grants.

AT-011  
Admin Owner can mutate; Analyst cannot mutate.

AT-012  
Soft delete restore works within 7 days; purge occurs after grace period.

AT-013  
Mobile layout remains usable for chat, mode switch, send, and step viewing.

## 11. Iterative Delivery Plan (2-Week Cycles)
Cycle 0 (Weeks 1-2)  
Foundation: repo structure, environment setup, Supabase + Railway + Vercel integration, auth baseline, Alembic migrations, arq worker scaffold, CI baseline.

Cycle 1 (Weeks 3-4)  
Room and agent management, pending/effective mode state machine, core room UX.

Cycle 2 (Weeks 5-6)  
Core chat: 3-mode LangGraph execution, NDJSON/SSE streaming timeline, direct agent chat, context budgeting/summarization, typed orchestrator routing contract.

Cycle 3 (Weeks 7-8)  
Tools only: Tavily search + file upload/read/parse (PDF/DOCX/TXT/MD/CSV) + arq job processing + permission enforcement + tool/file telemetry.

Cycle 4 (Weeks 9-10)  
Metering engine + credit accounting + pricing versioning + wallet/usage pages (no Stripe yet).

Cycle 5 (Weeks 11-12)  
Admin analytics and controls + reporting rollups.

Cycle 6 (Weeks 13-14)  
Stripe integration for subscriptions and top-ups + webhook idempotency + billing operations checks.

Cycle 7 (Weeks 15-16)  
Hardening: QA, load checks, runbooks, retention jobs, staging-to-prod launch readiness.

Timeline commitment: approximately 15-16 weeks for a 1-2 engineer team.

## 12. Deployment Requirements
Environments:
1. Dev
2. Staging
3. Prod

Hosting:
1. Frontend: Vercel
2. API + Worker: Railway
3. DB/Auth/Storage: Supabase
4. Queue: Redis

Release requirements:
1. CI checks on pull request (lint/test/build).
2. Staging deployment before production promotion.
3. Production deploy with rollback procedure documented.

## 13. Risks and Mitigations
Risk 1: Model/provider cost drift.  
Mitigation: versioned pricing tables, daily reconciliation, admin alerts.

Risk 2: Workflow quality inconsistency across modes.  
Mitigation: deterministic prompts/contracts + regression test suite.

Risk 3: File parsing failures on edge documents.  
Mitigation: async retries, clear fallback UX, parser-specific telemetry.

Risk 4: Small team bandwidth (1-2 engineers).  
Mitigation: strict scope control, staged rollouts, feature flags for non-critical items.
