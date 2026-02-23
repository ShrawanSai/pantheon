# Pantheon Frontend Plan (Authoritative)

Version: 2.0
Date: 2026-02-23
Status: Approved for implementation

## 1. Purpose
This is the single frontend source of truth for MVP implementation. It merges:
- scope and delivery structure from `docs/frontend_development_plan.md`
- implementation detail from prior `docs/frontend_plan.md`

It is aligned to:
- `docs/mvp_srs.md`
- `docs/mvp_wireframes.md`
- `docs/mvp_master_plan.md`
- backend routes in `apps/api/app/api/v1/routes/*`

## 2. Current Baseline

### 2.1 Frontend state
- Existing app: `apps/web` (Next.js app router scaffold)
- Existing pages are placeholders:
  - `/`
  - `/auth/login`
  - `/auth/callback`
- No production UX, no API client layer, no streaming UI

### 2.2 Backend readiness (implemented and usable)
- Auth: `GET /api/v1/auth/me`
- Rooms: create/list/read/delete, patch mode, room-agent assignment
- Agents: create/list/read/update/delete
- Sessions:
  - room session create/list
  - standalone agent session create/list
  - message history read
  - turn history read
  - non-streaming turn submit
  - streaming turn submit (SSE)
- Files: room file upload + async parse lifecycle
- Users: wallet, usage, transactions, top-up intent
- Admin: pricing, settings, usage summary, analytics, wallet inspect, grants

### 2.3 Backend gaps to track
- Separate admin auth system is not implemented yet (current admin gate is user-id allowlist)
- Some original master-plan admin controls are not yet exposed as APIs (caps/suspend/model-access rules)
- F70 staging deploy drift is deployment-only, not a frontend code blocker

## 3. Locked Technical Decisions

| Concern | Decision |
|---|---|
| Framework | Next.js app router + TypeScript |
| Styling | Tailwind CSS + shadcn/ui |
| Icons | lucide-react |
| Server state | TanStack Query v5 |
| Client UI state | Zustand |
| Forms | React Hook Form + Zod |
| Auth | `@supabase/ssr` with middleware |
| Streaming transport | `fetch` + `ReadableStream` parser |
| Markdown render | react-markdown + remark-gfm |
| Charts | recharts |
| Payments UI | Stripe Elements |

Rules:
- Do not use EventSource for turn streaming because Authorization headers are required.
- Do not expose service role secrets in frontend.

## 4. Design System

### 4.1 Color tokens
- `bg.app`: `#09090b`
- `bg.surface`: `#18181b`
- `bg.raised`: `#27272a`
- `border.default`: `#3f3f46`
- `text.primary`: `#fafafa`
- `text.muted`: `#a1a1aa`
- `accent.primary`: `#8b5cf6`
- `status.success`: `#22c55e`
- `status.warning`: `#f59e0b`
- `status.error`: `#ef4444`

### 4.2 Typography
- Primary font: Inter
- Mono font: JetBrains Mono
- Base size: 14px

### 4.3 Agent color policy
- Position 1: sky
- Position 2: violet
- Position 3: emerald
- Position 4+: amber
- Manager synthesis: neutral gray

## 5. Route and Information Architecture

### 5.1 Public/auth
- `/`
- `/auth/login`
- `/auth/callback`

### 5.2 User app
- `/rooms`
- `/rooms/new`
- `/rooms/[roomId]`
- `/rooms/[roomId]/settings`
- `/agents`
- `/agents/new`
- `/agents/[agentId]/edit`
- `/billing`

### 5.3 Admin
- `/admin`
- `/admin/analytics`
- `/admin/pricing`
- `/admin/users`

## 6. Core Screen Specs

### 6.1 Home dashboard
- Recent rooms list
- Quick-start templates
- usage snapshot and billing shortcut

### 6.2 Room create/edit
- Room identity fields
- Mode selector
- Agent assignment and order
- Save semantics and validation

### 6.3 Workspace (primary screen)
Desktop: 3-panel layout
- left: room info + roster
- center: timeline + chat input
- right: files + tool activity + usage

Mobile:
- single main timeline
- tabbed secondary panels (chat/tools/files)

### 6.4 Direct agent chat
- standalone session entry from agent detail/list
- same timeline and composer surface, scoped to agent session

### 6.5 Billing
- wallet balance
- usage list
- transaction history
- top-up flow initiation and payment confirmation UX

### 6.6 Admin dashboard
- pricing multipliers
- enforcement toggle and effective settings
- usage summary bucketed charts/tables
- usage and active-user analytics
- wallet lookup and grants

## 7. Streaming UX Specification (Mandatory)

### 7.1 Transport and parser
- Use `POST /api/v1/sessions/{session_id}/turns/stream`
- Parse `text/event-stream` payload using `fetch` + `ReadableStream`
- Each `data: {json}` event updates in-memory stream state

### 7.2 Event handling contract
Current backend emits:
- `chunk` with `delta`
- `round_start` with `round`
- `round_end` with `round`
- `done` with `turn_id`, `provider_model`, optional `balance_after`, `low_balance`, `summary_used_fallback`

### 7.3 Visual behavior
- Create an agent bubble immediately when a step starts logically (first delta for that agent if no explicit step event)
- Append token deltas live into that bubble
- Keep per-agent bubbles separate (never merge specialist and manager text)
- Show round dividers for orchestrator multi-round flow
- Append manager synthesis as distinct section/bubble
- Auto-scroll to bottom unless user has manually scrolled up
- On stream completion, unlock composer and refetch canonical turn/messages

### 7.4 Failure behavior
- Stream parse error: show inline failure state and offer non-stream retry
- Backend 422 when tools + stream not supported: show actionable banner and allow fallback to non-stream send
- Backend 402/429: show explicit blocking message and keep draft text

## 8. Component Architecture

### 8.1 Layout components
- `AppShell`
- `Sidebar`
- `Topbar`
- `MobileNav`

### 8.2 Workspace components
- `RoomWorkspace`
- `ConversationTimeline`
- `UserBubble`
- `AgentBubble`
- `ManagerSynthesisBubble`
- `RoundDivider`
- `StreamingIndicator`
- `ChatInput`
- `ModeSelector`
- `TurnDetailsDrawer`
- `AgentRoster`
- `FilePanel`
- `ToolActivityPanel`
- `UsagePanel`

### 8.3 Entity components
- `RoomCard`
- `RoomForm`
- `RoomAgentAssignment`
- `AgentCard`
- `AgentForm`

### 8.4 Billing/admin components
- `WalletCard`
- `UsageChart`
- `TransactionTable`
- `TopUpModal`
- `PricingEditor`
- `EnforcementControls`
- `AdminAnalyticsPanel`
- `AdminWalletInspector`

## 9. Folder Structure (Locked)

```text
apps/web/src/
  app/
    (authed)/
      layout.tsx
      rooms/
      agents/
      billing/
      admin/
    auth/
      login/page.tsx
      callback/page.tsx
    globals.css
    layout.tsx

  components/
    ui/
    layout/
    room/
    agents/
    billing/
    admin/
    common/

  lib/
    api/
      client.ts
      rooms.ts
      agents.ts
      sessions.ts
      files.ts
      users.ts
      admin.ts
    hooks/
    stores/
    supabase/
      client.ts
      server.ts
      middleware.ts
    utils/
      formatting.ts
      streaming.ts

  types/
    api.ts
    events.ts

  middleware.ts
```

## 10. API Integration Matrix

### 10.1 User app
- Auth: `GET /api/v1/auth/me`
- Rooms:
  - `POST /api/v1/rooms`
  - `GET /api/v1/rooms`
  - `GET /api/v1/rooms/{room_id}`
  - `DELETE /api/v1/rooms/{room_id}`
  - `PATCH /api/v1/rooms/{room_id}/mode`
- Room agents:
  - `POST /api/v1/rooms/{room_id}/agents`
  - `GET /api/v1/rooms/{room_id}/agents`
  - `DELETE /api/v1/rooms/{room_id}/agents/{agent_id}`
- Agents:
  - `POST /api/v1/agents`
  - `GET /api/v1/agents`
  - `GET /api/v1/agents/{agent_id}`
  - `PATCH /api/v1/agents/{agent_id}`
  - `DELETE /api/v1/agents/{agent_id}`
- Sessions:
  - `POST /api/v1/rooms/{room_id}/sessions`
  - `GET /api/v1/rooms/{room_id}/sessions`
  - `POST /api/v1/agents/{agent_id}/sessions`
  - `GET /api/v1/agents/{agent_id}/sessions`
  - `GET /api/v1/sessions/{session_id}/messages`
  - `GET /api/v1/sessions/{session_id}/turns`
  - `POST /api/v1/sessions/{session_id}/turns`
  - `POST /api/v1/sessions/{session_id}/turns/stream`
- Files:
  - `POST /api/v1/rooms/{room_id}/files`
- Billing/user:
  - `GET /api/v1/users/me/wallet`
  - `POST /api/v1/users/me/wallet/top-up`
  - `GET /api/v1/users/me/usage`
  - `GET /api/v1/users/me/transactions`

### 10.2 Admin
- Pricing:
  - `GET /api/v1/admin/pricing`
  - `PATCH /api/v1/admin/pricing/{model_alias}`
- Settings:
  - `GET /api/v1/admin/settings`
  - `PATCH /api/v1/admin/settings/enforcement`
  - `DELETE /api/v1/admin/settings/enforcement`
- Usage summary:
  - `GET /api/v1/admin/usage/summary`
- Analytics:
  - `GET /api/v1/admin/analytics/usage`
  - `GET /api/v1/admin/analytics/active-users`
- Wallet ops:
  - `GET /api/v1/admin/wallets/{user_id}`
  - `POST /api/v1/admin/wallets/{user_id}/grant`
  - `POST /api/v1/admin/users/{user_id}/wallet/grant`

## 11. State and Data Strategy
- TanStack Query for all server data fetching, cache, invalidation, pagination
- Zustand for local UI state only:
  - sidebar open/closed
  - active mobile tab
  - stream in-flight buffer per session
  - drawer/modal visibility
- No ad-hoc duplicated fetch state in components

## 12. Error and Status Standards

| HTTP/status | UI behavior |
|---|---|
| 401 | clear session and redirect to login |
| 403 | permission denied screen or inline guard message |
| 404 | not found state, no resource leakage copy |
| 422 | inline form validation errors |
| 429 | rate-limit banner with retry hint |
| 402 | insufficient credits callout in composer area |
| 5xx | generic error state + retry action |
| stream error | keep draft, unlock input, offer non-stream resend |

Loading/empty/error states are required for every data surface.

## 13. Mobile Behavior (Required)
- Sidebar becomes drawer
- Workspace collapses to single-column timeline
- Secondary panes become tab views
- Composer remains sticky at bottom
- Drawer and sheet interactions must be keyboard-accessible and touch-friendly

## 14. Delivery Order (No schedule estimates)

### Phase A - Foundation
- auth, app shell, API client, route protection

### Phase B - Entities and navigation
- rooms, agents, assignment, session bootstrapping

### Phase C - Workspace and streaming
- timeline, composer, stream parser, round visualization, history replay

### Phase D - Files and tool-aware UX
- uploader, parse status, file context affordances

### Phase E - Billing and top-up
- wallet, usage, transactions, top-up UX

### Phase F - Admin surfaces
- pricing, settings, analytics, wallet grants

### Phase G - Hardening
- accessibility, performance, E2E, release polish

## 15. Testing and Quality Gates
- Unit: parsing, adapters, formatting, reducer/store logic
- Integration: screen-level data and mutation behavior
- E2E critical flows:
  1. login and bootstrap
  2. room session turn (non-stream and stream)
  3. standalone agent session turn and history reload
  4. file upload and parsed usage in conversation
  5. wallet/top-up flow
  6. admin pricing and analytics flow

Done criteria for frontend MVP:
1. All UI-002 core screens are fully functional
2. Streaming UX works for room and standalone turn flows
3. Conversation history is durable and reloadable
4. Billing and admin views are functional and guarded
5. Mobile core flows are usable and tested

## 16. Open Dependencies and Risks
- F70 staging parity must be resolved by deployment action
- Product-owner thresholds in `docs/enforcement_production_criteria.md` remain external inputs
- Admin auth hardening remains a backend dependency for full production governance
