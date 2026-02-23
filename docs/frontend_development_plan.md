# Pantheon Frontend Development Plan

Date: 2026-02-23  
Scope: Full MVP frontend delivery based on current requirements and backend through Week 23.

## 1. Goal
Deliver the full production-ready web frontend for Pantheon:
- chat-first user experience
- room + standalone agent workflows
- streaming turn UI
- file and tool-aware conversations
- wallet, top-up, usage, transaction pages
- internal admin dashboard for pricing, enforcement, wallets, analytics

This plan is aligned to:
- `docs/mvp_srs.md` (UI-001 to UI-005, FR groups)
- `docs/mvp_wireframes.md`
- `docs/mvp_master_plan.md`
- implemented backend API surface in `apps/api/app/api/v1/routes`

## 2. Current Baseline

## 2.1 Existing frontend state
- `apps/web` exists with Next.js app-router scaffold.
- Current pages are placeholders:
  - `/`
  - `/auth/login`
  - `/auth/callback`
- No real product flows are implemented yet.

## 2.2 Backend readiness (usable now)
Available and stable endpoint families:
- auth: `/api/v1/auth/me`
- rooms: CRUD + mode patch + room-agent assignment
- agents: CRUD
- sessions:
  - room sessions
  - standalone agent sessions
  - history reads (`/messages`, `/turns`)
  - non-streaming turns
  - streaming turns (SSE)
- files: room file upload and async parsing workflow
- users: wallet, usage, transactions, top-up intent
- admin:
  - pricing read/update
  - enforcement settings (read/patch/delete)
  - usage summary (day/week/month bucket)
  - analytics usage + active users
  - wallet inspection + grants
- webhooks: Stripe webhook endpoint

## 2.3 Backend gaps to track (not blockers for most UI)
From current requirements vs implementation:
- Separate admin auth system is not yet implemented (current admin check is allowlist by user ID).
- Some master-plan admin controls (caps/suspend/model-access rules) are not yet implemented as APIs.
- F70 staging parity depends on redeploy state, not frontend code.

## 3. Frontend Architecture

## 3.1 Stack
- Next.js app-router + TypeScript (continue existing `apps/web`)
- Supabase Auth client for magic-link flow
- Typed API layer (zod-validated DTOs for requests/responses)
- Query/cache layer (TanStack Query recommended)
- SSE client utility for turn streaming
- Stripe Elements for top-up checkout confirmation

## 3.2 App structure
- Route groups:
  - `(auth)` login/callback
  - `(app)` user product UI
  - `(admin)` admin UI
- Shared modules:
  - `lib/api` (http client, auth headers, error mapping)
  - `lib/sse` (event parser + reconnect strategy)
  - `lib/session` (token/session handling)
  - `components/ui` (design system primitives)
  - `features/*` (rooms, agents, chat, billing, admin analytics)

## 3.3 Core UX rules
- Chat-first shell with persistent left navigation.
- Timeline-first conversation UI (agent outputs shown separately).
- Mobile-first responsive behavior for core flows.
- Explicit state banners for mode, enforcement warnings, and stream state.

## 4. Screen and Feature Map

## 4.1 User app
1. Home/Dashboard  
- recent rooms, usage snapshot, quick actions.

2. Agent Management  
- create/list/update/delete standalone agents.

3. Room Management  
- create/list/detail/delete rooms.
- assign/unassign agents to rooms.
- patch room mode (`manual`, `roundtable`, `orchestrator`).

4. Session Management  
- create/list room sessions.
- create/list standalone sessions.
- open session timeline with full history.

5. Workspace (room and standalone)  
- message timeline from `/sessions/{id}/messages`
- turn history from `/sessions/{id}/turns`
- non-stream turn send
- stream turn send via `/turns/stream`
- mode-aware rendering:
  - manual/tag outputs
  - roundtable sequential outputs
  - orchestrator multi-round synthesis output

6. Files and tool context  
- upload files to room
- parse-status UI (`pending/completed/failed`)
- file reference helper in composer

7. Billing  
- wallet balance page
- usage list with filters/pagination
- transaction history
- top-up initiation (PaymentIntent client secret flow)

## 4.2 Admin app
1. Pricing panel  
- view active pricing version
- patch model multiplier

2. Enforcement settings  
- effective config view
- runtime override patch/clear

3. Usage summary  
- totals + model breakdown
- bucket selector: day/week/month

4. Analytics  
- usage analytics by user/model and date range
- active users (`day/week/month`)

5. Wallet operations  
- inspect user wallet and recent transactions
- admin grants

## 5. Phased Delivery Plan

## Phase A - Foundation and Auth (1 week)
Deliverables:
- app shell + route protection
- Supabase login + callback + session persistence
- API client with auth header injection
- global error and loading patterns

Acceptance:
- User can sign in, persist session, sign out.
- Unauthorized pages redirect to login.
- `/api/v1/auth/me` bootstrap works.

## Phase B - Entities and Navigation (1 to 1.5 weeks)
Deliverables:
- Rooms CRUD + mode patch UI
- Agents CRUD UI
- Room-agent assignment UI
- Session create/list pages (room + standalone)

Acceptance:
- Full navigation between home, rooms, agents, sessions.
- Ownership and 404/403 cases handled gracefully.

## Phase C - Conversation and History (2 weeks)
Deliverables:
- Workspace page for room and standalone sessions
- Timeline rendering from messages endpoint
- Turn history side panel
- Composer with non-stream and stream mode
- SSE parser for events:
  - `chunk`
  - `round_start`
  - `round_end`
  - `done` (captures `balance_after`, `low_balance`, `summary_used_fallback`)

Acceptance:
- Full conversation history reload works after days/weeks.
- Stream reconnect failure handling degrades to non-stream retry.
- Mode-specific output is visible and traceable in timeline.

## Phase D - Files and Tool-aware UX (1 week)
Deliverables:
- Room file uploader
- parse-status polling UI
- failed parse and pending-state UX
- quick-insert file reference in prompt composer

Acceptance:
- upload, parse transition, and subsequent conversation usage all visible in UI.

## Phase E - Billing and Top-up (1 week)
Deliverables:
- Wallet page
- Usage page
- Transactions page
- Top-up intent flow with Stripe Elements confirmation UX

Acceptance:
- User can start top-up flow and see resulting wallet changes after webhook processing.
- balance warnings (`low_balance`) surfaced in workspace.

## Phase F - Admin Dashboard (1.5 weeks)
Deliverables:
- Admin pricing/editor
- Enforcement settings panel
- Usage summary and analytics pages
- Admin wallet lookup + grant action

Acceptance:
- All admin pages enforce role checks.
- Analytics filters, pagination, and chart/table states are production-ready.

## Phase G - Hardening, QA, and Release (1 week)
Deliverables:
- E2E tests for critical flows
- accessibility pass (keyboard + aria + contrast)
- performance pass (bundle split + route-level loading states)
- Sentry frontend integration
- release checklist and rollback playbook

Acceptance:
- Beta-ready frontend release candidate.

## 6. API Integration Matrix

User product:
- Auth: `GET /api/v1/auth/me`
- Rooms: `POST/GET/GET{id}/DELETE/PATCH mode`
- Room agents: `POST/GET/DELETE`
- Agents: `POST/GET/GET{id}/PATCH/DELETE`
- Sessions:
  - `POST /rooms/{room_id}/sessions`
  - `GET /rooms/{room_id}/sessions`
  - `POST /agents/{agent_id}/sessions`
  - `GET /agents/{agent_id}/sessions`
  - `GET /sessions/{session_id}/messages`
  - `GET /sessions/{session_id}/turns`
  - `POST /sessions/{session_id}/turns`
  - `POST /sessions/{session_id}/turns/stream`
- Files: `POST /rooms/{room_id}/files`
- Billing/user:
  - `GET /users/me/wallet`
  - `POST /users/me/wallet/top-up`
  - `GET /users/me/usage`
  - `GET /users/me/transactions`

Admin:
- Pricing: `GET/PATCH /admin/pricing`
- Settings: `GET /admin/settings`, `PATCH/DELETE /admin/settings/enforcement`
- Summary: `GET /admin/usage/summary`
- Analytics: `GET /admin/analytics/usage`, `GET /admin/analytics/active-users`
- Wallets:
  - `GET /admin/wallets/{user_id}`
  - `POST /admin/wallets/{user_id}/grant`
  - `POST /admin/users/{user_id}/wallet/grant`

## 7. Testing Strategy
- Unit:
  - api client adapters
  - SSE parser
  - formatter/util modules
- Integration:
  - page-level data loading and mutations
  - auth/session bootstrap
- E2E:
  1. Login -> create room -> assign agents -> create session -> send turn
  2. Standalone agent session turn with history reload
  3. Streaming turn with round events
  4. File upload + parse completion + file-informed turn
  5. Wallet top-up initiation + transaction visibility
  6. Admin pricing update and analytics filters

## 8. Release Gates for "Full Frontend"
Frontend is considered complete when all are true:
1. All six core screens from SRS UI-002 are fully functional.
2. Room and standalone chat both support history, non-stream, and stream.
3. Billing and top-up user flows are working end-to-end.
4. Admin analytics and control pages are functional.
5. Mobile responsive behavior passes for core flows.
6. E2E suite green in CI.
7. Staging points to backend head compatible with Weeks 14-23+ APIs.

## 9. Suggested Execution Order
1. Phase A + B first (foundation + entities).
2. Phase C next (workspace and streaming), because it is highest product risk.
3. Phase D + E (files and billing).
4. Phase F (admin).
5. Phase G (hardening and release).

This sequence gives usable user value early while reducing risk in the conversation runtime UI.
