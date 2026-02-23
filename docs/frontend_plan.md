# Pantheon Frontend Plan

Version: 1.0
Date: 2026-02-23
Status: Approved for implementation

---

## 1. Current State

The frontend scaffold exists at `apps/web/` with:
- Next.js 15 App Router, TypeScript
- Only pages: `/` (connectivity check), `/auth/login`, `/auth/callback`
- No real UI, no component library, no state management, no API layer

Everything described below is greenfield.

---

## 2. Tech Stack (Locked)

| Concern | Choice | Reason |
|---|---|---|
| Framework | Next.js 15 App Router | Already in repo |
| Language | TypeScript (strict) | Already in repo |
| Styling | Tailwind CSS v3 | Fast, consistent, no CSS files to manage |
| Component library | shadcn/ui | Radix UI primitives + Tailwind, unstyled by default, easy to own |
| Icons | lucide-react | Ships with shadcn/ui, consistent set |
| State (server) | TanStack Query v5 | Cache, pagination, refetch, optimistic updates |
| State (client) | Zustand | Lightweight, no boilerplate, good for UI state |
| Auth | @supabase/ssr | First-party Next.js App Router support, handles cookies |
| Streaming | Native `fetch` + `ReadableStream` | SSE-compatible, no library needed |
| Forms | React Hook Form + Zod | Validation consistency, matches backend Pydantic contracts |
| Markdown | react-markdown + remark-gfm | Agent outputs often include markdown |

---

## 3. Design Principles

1. **Familiar over clever.** Users should feel at home immediately. Reference: ChatGPT layout, Slack sidebar structure.
2. **Dark-first.** Dark background (`zinc-900`/`zinc-950`), light text. Match what users expect from AI tools.
3. **Streaming is the UX.** Agent responses should appear token by token. No "loading spinner then dump". Every agent gets its own bubble that fills in live.
4. **Transparency is a feature.** Multi-agent outputs are separate bubbles with agent name + model label. Credits per turn are always visible. This is Pantheon's differentiator — do not collapse or hide it.
5. **Mode is always visible.** The current active mode (Manual / Roundtable / Orchestrator) must be displayed in the input bar at all times. Mode changes apply on next send — communicate this clearly.
6. **Mobile is a first-class citizen.** The 3-panel desktop layout collapses to a tab-based single-panel view on mobile.

---

## 4. Color and Typography

### Palette
```
Background:     zinc-950  (#09090b)
Surface:        zinc-900  (#18181b)
Surface-raised: zinc-800  (#27272a)
Border:         zinc-700  (#3f3f46)
Text-primary:   zinc-50   (#fafafa)
Text-muted:     zinc-400  (#a1a1aa)
Accent:         violet-500 (#8b5cf6)  — primary actions, active states
Success:        emerald-500
Warning:        amber-500
Error:          red-500
```

### Agent color coding (per position in room, cycles)
```
Position 1: sky-400
Position 2: violet-400
Position 3: emerald-400
Position 4: amber-400
Manager:    zinc-300 (neutral — the orchestrator)
```

### Typography
- Font: `Inter` (Google Fonts, already standard for SaaS)
- Base: 14px / 1.5 line height
- Code/preformatted: `JetBrains Mono`

---

## 5. Application Routes

```
/                         → redirect to /rooms (if authed) or /auth/login
/auth/login               → magic link entry (already exists)
/auth/callback            → Supabase callback handler (already exists)

/rooms                    → Home dashboard (room list + quick-start templates)
/rooms/new                → Create room flow
/rooms/[roomId]           → Room workspace (the main chat screen)
/rooms/[roomId]/settings  → Edit room name, goal, mode default, agents

/agents                   → Agent library (all user's agents)
/agents/new               → Create agent
/agents/[agentId]/edit    → Edit agent

/billing                  → Wallet balance, usage breakdown, transaction history, top-up

/admin                    → Admin dashboard (guard: admin role required)
/admin/users              → User list with cap/suspend controls
/admin/analytics          → Usage + active-user charts
/admin/pricing            → Model multiplier editor
```

---

## 6. Layout Structure

### 6.1 Root Layout (all authed pages)

```
┌─────────────────────────────────────────────────────────┐
│ Sidebar (240px, collapsible)  │  Page Content             │
│                               │                           │
│  [Pantheon logo]              │                           │
│                               │                           │
│  + New Room                   │                           │
│                               │                           │
│  ROOMS                        │                           │
│  > Weekly Memo                │                           │
│  > Contract Review            │                           │
│  > Research Digest            │                           │
│                               │                           │
│  ────                         │                           │
│  Agents                       │                           │
│  Billing                      │                           │
│  ────                         │                           │
│  [Avatar] user@email   [⚙]   │                           │
│  120 / 495 cr          [≡]   │                           │
└─────────────────────────────────────────────────────────┘
```

The sidebar is always visible on desktop (≥1024px). Below 1024px it becomes a slide-over drawer triggered by a hamburger button in the topbar.

### 6.2 Room Workspace Layout (3-panel, desktop)

```
┌──────────────┬───────────────────────────────┬──────────────┐
│ Left Panel   │ Conversation Timeline          │ Right Panel  │
│ (240px)      │ (flex-1)                       │ (280px)      │
│              │                                │              │
│ Room name    │ [scrollable message list]      │ Tool Activity│
│ Mode badge   │                                │ Files        │
│              │                                │ Usage        │
│ Agents       │                                │              │
│ (roster)     │                                │              │
│              │                                │              │
│              ├────────────────────────────────┤              │
│              │ ChatInput (sticky bottom)      │              │
└──────────────┴────────────────────────────────┴──────────────┘
```

Right panel is collapsible (toggle button). On screens 1024–1280px, right panel hides by default.

### 6.3 Mobile Layout (< 768px)

```
┌──────────────────────────┐
│ Topbar: [≡] Room Name    │
├──────────────────────────┤
│                          │
│ Conversation Timeline    │
│                          │
├──────────────────────────┤
│ [Chat] [Tools] [Files]   │  ← tab bar
├──────────────────────────┤
│ ChatInput                │
└──────────────────────────┘
```

---

## 7. Key Components

### 7.1 ChatInput

The single most important component.

```
┌────────────────────────────────────────────────────────┐
│ [Mode: Orchestrator ▾]  [@tag...]  [📎]                │
│ ┌──────────────────────────────────────────────────┐   │
│ │ Ask anything...                                  │   │
│ └──────────────────────────────────────────────────┘   │
│                                          [Send ↵]       │
└────────────────────────────────────────────────────────┘
```

- **Mode selector**: dropdown showing Manual / Roundtable / Orchestrator. Shows current effective mode. If pending mode differs, show `"Orchestrator (applies on next send)"` tooltip.
- **@tag input** (Manual mode only): autocompletes to agent names in the room roster. Shows chips for selected agents.
- **File attach**: opens file picker (PDF/DOCX/TXT/MD/CSV). Shows attached file chips below textarea.
- **Textarea**: auto-resizes. `Shift+Enter` = newline, `Enter` = send.
- **Send button**: disabled during in-flight turn. Shows spinner.

### 7.2 AgentBubble

Each agent response is a distinct bubble — never merged.

```
┌──────────────────────────────────────────────────────┐
│ [●] Researcher · DeepSeek          2.1s  1.12 cr  [↗]│
│                                                      │
│  Here are the key findings from the document...      │
│  ▌ (cursor while streaming)                          │
└──────────────────────────────────────────────────────┘
```

- Colored dot = agent color (by position)
- Agent name + model alias always visible
- Latency + credits shown after completion (hidden during streaming)
- `[↗]` expands to Turn Details Drawer
- Streaming: text appends token by token. Cursor blinks. No layout shift.

### 7.3 OrchestratorRoundBadge

When orchestrator multi-round is active, show round boundaries:

```
─────────── Round 2 of 3 ───────────
```

Rendered as a centered muted divider between round groups.

### 7.4 ManagerSynthesisBubble

Final synthesis from manager (orchestrator mode):

```
┌──────────────────────────────────────────────────────┐
│ [◆] Manager Synthesis                     0.3 cr  [↗]│
│                                                      │
│  Based on the specialist outputs...                  │
└──────────────────────────────────────────────────────┘
```

Diamond icon, `zinc-300` color to distinguish from specialists.

### 7.5 TurnDetailsDrawer

Slide-over from the right, triggered by `[↗]` on any bubble.

```
Turn #12 · Orchestrator

Step 1  Researcher (DeepSeek)      ✓  2.1s
  Prompt: 1,120  Output: 340  Cached: 900  Credits: 1.12

Step 2  Writer (GPT-OSS)           ✓  3.3s
  Prompt: 1,870  Output: 420  Cached: 1,020  Credits: 1.74

Tool Calls: search ×2, fetch ×1   Tool Credits: 0.80
Total: 4.60 credits
```

### 7.6 ModeChangeBanner

When the user changes mode, show a non-intrusive inline banner in the timeline:

```
  ── Mode changed to Orchestrator · applies on next send ──
```

This is a system message in the timeline, not a toast.

### 7.7 StreamingIndicator

Per-agent "thinking" state while waiting for first token:

```
[●] Researcher · DeepSeek
   ···  (three dots pulsing)
```

Appears immediately when step starts, before first token arrives.

---

## 8. API Layer

### Structure

```
apps/web/src/
  lib/
    api/
      client.ts        ← base fetch wrapper (auth headers, error parsing)
      agents.ts
      rooms.ts
      sessions.ts
      turns.ts
      files.ts
      users.ts
      admin.ts
    hooks/
      useRooms.ts
      useRoom.ts
      useAgents.ts
      useSession.ts
      useSendTurn.ts       ← non-streaming
      useStreamTurn.ts     ← SSE streaming
      useWallet.ts
      useAdminAnalytics.ts
    stores/
      uiStore.ts           ← Zustand: sidebar open, active panel, drawer state
      streamStore.ts       ← Zustand: in-flight streaming state per session
```

### Base Client

```typescript
// lib/api/client.ts
async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const session = await getSupabaseSession();
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${session.access_token}`,
      ...init?.headers,
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, err.detail ?? "Unknown error");
  }
  return res.json() as Promise<T>;
}
```

### Streaming Hook

```typescript
// lib/hooks/useStreamTurn.ts
// Consumes POST /sessions/{id}/turns/stream (NDJSON/SSE)
// Emits events: turn_started, step_started, step_delta, step_completed,
//               turn_completed, turn_failed, round_start, round_end

function useStreamTurn(sessionId: string) {
  // Uses fetch + ReadableStream + TextDecoder
  // Parses newline-delimited JSON
  // Dispatches to streamStore
  // On turn_completed: invalidates TanStack Query cache for session messages
}
```

---

## 9. Auth Flow

Uses `@supabase/ssr`:

1. `/auth/login` — user enters email, Supabase sends magic link
2. `/auth/callback` — Supabase redirects here with code, exchange for session, redirect to `/rooms`
3. **Middleware** (`middleware.ts`) — runs on all routes except `/auth/*` and `/api/*`. If no valid session cookie → redirect to `/auth/login`
4. **Session refresh** — `@supabase/ssr` handles automatic token refresh via middleware

Admin routes (`/admin/*`) additionally check for `admin_role` claim in the JWT. If absent → 403 page.

---

## 10. Streaming UX — Detailed Behavior

This is the most critical UX surface. Get it right.

### Event sequence (orchestrator mode, 2 rounds):

```
turn_started          → show user message in timeline, lock ChatInput
round_start {round:1} → show "Round 1" divider
step_started {agent}  → append empty AgentBubble with pulsing dots
step_delta {text}     → append text to that bubble token by token
step_completed        → show latency + credits on bubble, hide cursor
step_started {agent}  → next agent bubble
...
round_end {round:1}
round_start {round:2} → show "Round 2" divider
...
step_started {manager}→ ManagerSynthesisBubble with pulsing dots
step_delta {text}     → stream synthesis
turn_completed        → unlock ChatInput, final credits
```

### Rules:
- Auto-scroll to bottom as new content arrives. Pause auto-scroll if user has scrolled up (detect scroll position).
- Each `step_started` must immediately render a bubble — do not wait for `step_delta`.
- `turn_failed` renders a red error bubble: `"Turn failed: {error_message}"`. ChatInput unlocks.
- On page load, existing messages render as static bubbles (no streaming animation).

---

## 11. Room Dashboard (Home)

```
/rooms
```

- **Quick Start Templates**: 5 cards — Inbox Copilot, Doc Review, Research Digest, KPI Review, + Blank. Clicking a template pre-fills the Create Room form.
- **Recent Rooms**: grid of room cards. Each shows name, mode badge, last used, credit cost this session.
- **Search**: filters rooms by name in real time (client-side filter on fetched list).
- **Credit summary**: top-right — `120 / 495 cr`. Clicking navigates to `/billing`.

---

## 12. Room Setup (Create/Edit)

Two-step form:

**Step 1 — Room**
- Name (required)
- Goal / description (optional, used in orchestrator system prompt)
- Default mode: radio (Manual / Roundtable / Orchestrator)

**Step 2 — Agents**
- Ordered list of agents. Drag to reorder.
- Each row: position number, agent name, model badge, tool permission badges (search, files)
- "+ Add Agent" opens a modal to pick from user's agent library or create inline
- Minimum 1 agent. Orchestrator mode requires ≥ 2.

Validation runs on submit. Errors appear inline, not as toasts.

---

## 13. Agent Library

```
/agents
```

- Grid of agent cards: name, model, tool permissions, "rooms using this"
- Create agent form:
  - Name
  - Agent key (auto-generated from name, editable)
  - Model: dropdown of supported aliases (llama, qwen, deepseek, gpt_oss, premium) with tier badges
  - Role Prompt: large textarea with character counter
  - Tools: checkboxes (web_search, file_read)

Agents are shared across rooms — one agent can be in multiple rooms.

---

## 14. Billing Page

```
/billing
```

Three sections:

**1. Plan & Balance**
```
Balance: 375.00 credits    Plan: Starter ($29/mo)
Used: 120 / 495  (24%)     [████░░░░░░]
Forecast: ~340 this month  [Upgrade Plan]
```

**2. Usage by Model** (this month)
Bar chart — model aliases on Y axis, credits on X axis. Uses `recharts` (lightweight).

**3. Transaction History**
Table: date, type (top_up / plan_grant / debit), amount, note, reference.

**Top-up flow**:
- "Add Credits" button → modal: amount input (min $1, max $500), shows credits preview
- Calls `POST /users/me/wallet/top-up` → gets Stripe `client_secret`
- Loads Stripe Elements inline (Payment Element) → user enters card
- On success → optimistic balance update + refetch wallet

---

## 15. Admin Dashboard

```
/admin
```

Guard: checks JWT for admin role. If not admin → show 403 page.

**Sections:**
1. Summary stats: DAU / WAU / MAU, total credits burned (30d), estimated margin
2. Top users by cost + top models by cost (two side-by-side tables)
3. User controls: input user ID → view wallet, set cap, suspend / reactivate
4. Pricing editor: table of model aliases + multipliers, inline editable
5. Audit log: last 50 actions, paginated

---

## 16. Error Handling Standards

| Scenario | Behavior |
|---|---|
| API 401 | Clear session, redirect to `/auth/login` |
| API 403 | Show inline "Permission denied" message |
| API 422 | Show field-level validation errors on form |
| API 429 | Show "Rate limit — please wait a moment" banner in ChatInput |
| API 5xx | Show "Something went wrong" with retry button |
| Stream error | Show red error bubble in timeline, unlock input |
| Network offline | Show "Connection lost" banner, auto-retry on reconnect |

Use a single `ApiError` class from the base client. Never show raw `detail` strings to users — map them to user-friendly messages.

---

## 17. Loading and Empty States

Every data-dependent surface needs three states:

| State | Treatment |
|---|---|
| Loading | Skeleton placeholder (not spinner) — match shape of content |
| Empty | Illustration + CTA. e.g. "No rooms yet — create your first room" |
| Error | Inline error message + "Retry" button |

Never use full-page spinners. Use skeletons for room list, agent list, message history.

---

## 18. File Upload Flow

In ChatInput:
1. User clicks 📎 → file picker opens (PDF/DOCX/TXT/MD/CSV, max 10MB)
2. File is uploaded immediately via `POST /api/v1/files`
3. While uploading: chip shows filename + progress bar
4. On success: chip shows filename + ✓. File ID stored in send payload.
5. On failure: chip shows red error, allow retry or remove
6. On send: `message` payload includes `file_ids: [...]`

Files uploaded to a session persist for the session lifetime — they remain accessible in subsequent turns without re-uploading.

---

## 19. Folder Structure

```
apps/web/src/
  app/                        ← Next.js App Router pages
    (authed)/                 ← route group — protected by middleware
      layout.tsx              ← root authed layout (sidebar + topbar)
      rooms/
        page.tsx              ← /rooms dashboard
        new/
          page.tsx            ← create room
        [roomId]/
          page.tsx            ← room workspace
          settings/
            page.tsx          ← room settings
      agents/
        page.tsx
        new/page.tsx
        [agentId]/edit/page.tsx
      billing/
        page.tsx
      admin/
        layout.tsx            ← admin guard
        page.tsx
        users/page.tsx
        analytics/page.tsx
        pricing/page.tsx
    auth/
      login/page.tsx
      callback/page.tsx
    globals.css
    layout.tsx                ← root layout (minimal, no sidebar)

  components/
    ui/                       ← shadcn/ui generated components
    layout/
      Sidebar.tsx
      Topbar.tsx
      MobileNav.tsx
    room/
      RoomWorkspace.tsx
      ConversationTimeline.tsx
      ChatInput.tsx
      AgentBubble.tsx
      ManagerSynthesisBubble.tsx
      RoundDivider.tsx
      TurnDetailsDrawer.tsx
      ModeSelector.tsx
      AgentRoster.tsx
      ToolActivityPanel.tsx
      FilePanel.tsx
      UsagePanel.tsx
    agents/
      AgentCard.tsx
      AgentForm.tsx
    billing/
      WalletCard.tsx
      UsageChart.tsx
      TransactionTable.tsx
      TopUpModal.tsx
    admin/
      UserControls.tsx
      AnalyticsPanel.tsx
      PricingEditor.tsx
      AuditLog.tsx
    common/
      CreditBadge.tsx
      ModelBadge.tsx
      ModeBadge.tsx
      SkeletonList.tsx
      EmptyState.tsx
      ErrorState.tsx
      ConfirmDialog.tsx

  lib/
    api/         ← fetch wrappers (see §8)
    hooks/       ← TanStack Query + streaming hooks
    stores/      ← Zustand stores
    supabase/
      client.ts  ← browser client
      server.ts  ← server client (for RSC)
      middleware.ts
    utils/
      formatting.ts   ← credit formatting, date formatting
      streaming.ts    ← NDJSON parser, SSE reader

  types/
    api.ts       ← TypeScript types matching backend schemas
    events.ts    ← streaming event types

  middleware.ts  ← route protection
```

---

## 20. Implementation Order

Build in this sequence. Each phase is independently shippable.

**Phase 1 — Foundation** (do this first, everything depends on it)
- Tailwind + shadcn/ui setup
- Supabase auth middleware
- Base API client
- Sidebar + authed layout
- `/rooms` dashboard with real data

**Phase 2 — Core Chat**
- Room workspace 3-panel layout
- Conversation timeline (static messages)
- ChatInput (non-streaming send)
- AgentBubble, UserBubble

**Phase 3 — Streaming**
- SSE streaming hook
- Live AgentBubble with token-by-token rendering
- Round dividers, ManagerSynthesisBubble
- StreamingIndicator (dots)

**Phase 4 — Room Management**
- Create Room form (2-step)
- Room Settings page
- Mode change banner in timeline
- ChatInput @tagging for manual mode

**Phase 5 — Agents**
- Agent library page
- Create/edit agent form

**Phase 6 — Files**
- File upload in ChatInput
- File panel in right sidebar
- Tool activity display

**Phase 7 — Billing**
- Wallet page
- Top-up modal (Stripe Elements)
- Transaction history

**Phase 8 — Admin**
- Admin layout + guard
- Analytics page
- User controls
- Pricing editor

**Phase 9 — Polish**
- TurnDetailsDrawer
- Mobile layout (tab-based)
- Empty + error states throughout
- Keyboard shortcuts (Cmd+K room search, Esc to close drawers)

---

## 21. Dependencies to Install

```bash
npm install tailwindcss @tailwindcss/typography postcss autoprefixer
npx shadcn-ui@latest init
npm install @tanstack/react-query zustand
npm install @supabase/supabase-js @supabase/ssr
npm install react-hook-form @hookform/resolvers zod
npm install react-markdown remark-gfm
npm install recharts
npm install @stripe/stripe-js @stripe/react-stripe-js
npm install lucide-react   # comes with shadcn, but explicit
```

---

## 22. Key Constraints

- **Never call the API from Server Components** — all data fetching goes through client-side TanStack Query hooks. This keeps auth token handling uniform and avoids RSC/streaming conflicts.
- **Never expose the Supabase service role key client-side** — only the anon key in `NEXT_PUBLIC_SUPABASE_ANON_KEY`.
- **Streaming endpoint** is `POST /sessions/{id}/turns/stream` — it requires `Authorization` header. This rules out `EventSource` (which doesn't support custom headers). Use `fetch` with `ReadableStream`.
- **Credit formatting** — always show 2 decimal places. `120.00 cr`, not `120 cr`.
- **Mode change** — `PATCH /rooms/{id}/mode` updates `pending_mode`. The effective mode for the next turn is set at turn execution time by the backend. The frontend must reflect this distinction clearly.
