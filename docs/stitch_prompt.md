# Pantheon — Production-Ready Stitch Build Prompt

> **Input Source:** `docs/ui_ux_developer_instructions.md`
> **Design Reference:** ChatGPT chat interface, adapted to a yellow/gray/white color palette

---

## 1. Project Overview

You are building **Pantheon** — an AI multi-agent orchestration platform delivered as a responsive web application. Pantheon lets users create custom AI agents (each with a unique personality, expertise, model, and tool access), assign them to collaborative "rooms," and run conversations where multiple agents work together. It is a **power tool for people who take AI seriously**.

### Core Concepts

- **Agent**: A custom AI persona with a name, system prompt (role), model alias, and optional tools (web search, file read). Users create agents like "Market Analyst" or "Tony Stark".
- **Room**: A workspace where agents are assigned. Each room has a collaboration mode.
- **Session**: A conversation thread within a room (or with a standalone agent).
- **Turn**: One user message + all the agent response(s) it triggers.

### Three Collaboration Modes

1. **Solo Chat (manual/tag)**: Direct 1-on-1 with a specific agent via `@agentkey` mention. User MUST tag an agent. Multiple @mentions auto-escalate to team discussion behavior.
2. **Team Discussion (roundtable)**: All assigned agents respond sequentially in position order. Each agent sees what previous agents said.
3. **Auto Best Answer (orchestrator)**: An AI routing manager reads the user's question, selects 1-3 specialists, gives them targeted instructions, evaluates if another round is needed (max 3 rounds), and synthesizes a final consolidated answer.

### Tech Stack

- **Frontend**: Next.js 14, React 18, TypeScript, Tailwind CSS 3.4, TanStack React Query v5, Zustand v5
- **Backend API**: FastAPI (Python), accessed via REST + SSE streaming
- **Auth**: Supabase Auth (magic link + dev password for localhost). JWT in `Authorization: Bearer {token}` header.
- **Payments**: Stripe (PaymentIntent flow for credit top-ups)
- **Icons**: lucide-react

### API Base URL
```
{NEXT_PUBLIC_API_BASE_URL}/api/v1
```
Default: `http://localhost:8000/api/v1`

All endpoints require `Authorization: Bearer {token}` unless noted.

Refer to `docs/ui_ux_developer_instructions.md` for the **complete API reference** (46 endpoints), SSE streaming protocol, request/response schemas, and all implementation details. That document is the single source of truth for API contracts.

---

## 2. Visual Language

### Design Philosophy

**ChatGPT-inspired layout and interaction patterns, reimagined in a warm yellow/gray/white palette.** The design borrows ChatGPT's clean minimalism, generous whitespace, and conversational flow — but replaces the neutral dark/green palette with a distinctive warm-toned identity.

The result should feel: **Clean. Warm. Professional. Trustworthy.** Like a premium productivity tool with personality.

### Color System

#### Light Mode (Primary — Default)

| Token | Hex | Usage |
|-------|-----|-------|
| `--bg-base` | `#FFFFFF` | Page background, main chat area |
| `--bg-sidebar` | `#F5F5F0` | Sidebar background (warm off-white) |
| `--bg-surface` | `#FAFAF5` | Cards, panels, elevated surfaces |
| `--bg-elevated` | `#F0F0EB` | Hover states, active sidebar items |
| `--bg-user-message` | `#FFF8E7` | User message bubble background (warm cream-yellow) |
| `--bg-input` | `#F7F7F2` | Input field background |
| `--accent` | `#D4A017` | Primary accent — warm gold/yellow (buttons, active states, links) |
| `--accent-hover` | `#B8860B` | Accent hover state — darker gold |
| `--accent-light` | `#FFF3CD` | Accent surface — very light yellow (badges, highlights) |
| `--accent-subtle` | `#FFFBEB` | Subtle accent backgrounds |
| `--text-primary` | `#1A1A1A` | Primary text — near-black |
| `--text-secondary` | `#6B7280` | Secondary text — medium gray |
| `--text-muted` | `#9CA3AF` | Placeholder text, timestamps |
| `--border` | `#E5E5E0` | Borders, dividers — warm gray |
| `--border-focus` | `#D4A017` | Focus ring — matches accent |
| `--success` | `#16A34A` | Success states, completed parse status |
| `--warning` | `#EAB308` | Warning states, pending parse status |
| `--error` | `#DC2626` | Error states, failed parse status |
| `--mode-solo` | `#0D9488` | Solo Chat mode badge — teal |
| `--mode-team` | `#EA580C` | Team Discussion mode badge — orange |
| `--mode-auto` | `#7C3AED` | Auto Best Answer mode badge — purple |

#### Dark Mode (Toggle Available)

| Token | Hex | Usage |
|-------|-----|-------|
| `--bg-base` | `#1A1A1A` | Page background |
| `--bg-sidebar` | `#141414` | Sidebar |
| `--bg-surface` | `#242424` | Cards, panels |
| `--bg-elevated` | `#2E2E2E` | Hover states |
| `--bg-user-message` | `#2E2A1F` | User message bubble (dark warm) |
| `--bg-input` | `#2E2E2E` | Input field |
| `--accent` | `#E5B31A` | Gold accent (brighter for dark bg) |
| `--accent-hover` | `#D4A017` | Accent hover |
| `--text-primary` | `#F5F5F0` | Primary text |
| `--text-secondary` | `#9CA3AF` | Secondary text |
| `--text-muted` | `#6B7280` | Muted text |
| `--border` | `#3A3A3A` | Borders |

### Typography

| Element | Font | Size | Weight | Line Height | Notes |
|---------|------|------|--------|-------------|-------|
| Body / Messages | `system-ui, -apple-system, "Segoe UI", sans-serif` | 16px | 400 | 1.6 | Identical to ChatGPT's reading comfort |
| Agent Name Labels | Same stack | 11px | 700 | 1 | Uppercase, letter-spacing 0.8px, mode-colored |
| H1 (Page Title) | Same stack | 24px | 600 | 1.3 | — |
| H2 (Section) | Same stack | 18px | 600 | 1.4 | — |
| Small / Caption | Same stack | 13px | 400 | 1.4 | Timestamps, metadata |
| Input Text | Same stack | 16px | 400 | 1.5 | Prevents iOS zoom (must be ≥16px) |
| Code Blocks | `"SF Mono", "Fira Code", "Consolas", monospace` | 14px | 400 | 1.5 | bg-surface, 12px padding, rounded-lg |

### Layout (ChatGPT-Inspired)

```
+------------------+--------------------------------------------+
|                  |                                            |
|  SIDEBAR         |           MAIN CHAT AREA                  |
|  260px           |                                            |
|  (collapsible)   |  +----------------------------------+     |
|                  |  |  Messages (max-width: 768px)     |     |
|  Room list       |  |  centered in available space     |     |
|  Session list    |  |                                  |     |
|  Agent panel     |  |  User msg → right-aligned with   |     |
|  File panel      |  |    warm cream-yellow bg, rounded  |     |
|                  |  |                                  |     |
|                  |  |  Agent msg → left-aligned, full   |     |
|                  |  |    width, no bubble, agent label  |     |
|                  |  |    above                          |     |
|                  |  |                                  |     |
|                  |  +----------------------------------+     |
|                  |                                            |
|                  |  +----------------------------------+     |
|                  |  |  INPUT BAR (pill-shaped,         |     |
|                  |  |  24px border-radius, centered)   |     |
|                  |  +----------------------------------+     |
+------------------+--------------------------------------------+
```

- **Sidebar**: 260px wide, collapsible on desktop, slides over on mobile (hamburger menu). Contains: room list, session list, agent panel, file panel.
- **Main area**: Fills remaining width. Messages constrained to `max-width: 768px`, centered.
- **Input bar**: Pill-shaped container (24–28px border-radius), sits at bottom of main area with 16px padding from edges. Contains text input, file upload button (📎), send button (circular, 36px, accent gold).
- **Mobile breakpoint** (`< 768px`): Sidebar hidden by default, hamburger toggle in header. Input bar full-width with 12px side padding.

### Spacing & Sizing

| Element | Value |
|---------|-------|
| Page padding | 0 (full-bleed sidebar + content) |
| Content max-width | 768px (messages), centered |
| Card border-radius | 12px |
| Button border-radius | 8px (rectangular), 50% (circular send button) |
| Modal border-radius | 16px |
| Input border-radius | 24px (pill-shaped chat input), 8px (form inputs) |
| Message vertical gap | 24px between turns, 8px between same-turn agent messages |
| Sidebar item padding | 12px horizontal, 10px vertical |
| Section spacing | 32px |
| Icon size | 20px default, 16px small |

### Animations & Transitions

| What | How |
|------|-----|
| Sidebar open/close | `transform: translateX()`, 200ms ease-out |
| Hover states | `background-color`, 150ms ease |
| Button press | `transform: scale(0.97)`, 100ms |
| Modal appearance | Fade in overlay (150ms) + slide up content (200ms ease-out) |
| Streaming text | Characters append in real-time, no animation on individual chars. Smooth scroll-to-bottom with `scrollIntoView({ behavior: 'smooth' })` |
| Page transitions | Minimal — instant route changes, data loaded via React Query with skeleton placeholders |
| Loading states | Subtle pulse animation on skeleton elements (opacity 0.5 → 1, 1.5s ease-in-out infinite) |

---

## 3. Page-by-Page UI Plan

### 3.1 Login Page (`/auth/login`)

**Layout**: Centered card on a `--bg-base` background. No sidebar.

**Elements**:
- Pantheon logo/wordmark at top (golden accent color)
- Heading: "Welcome to Pantheon"
- Subheading: "Your AI council awaits." (muted text)
- Email input field (pill-shaped, 48px height)
- "Send Magic Link" button (full-width, accent gold bg, white text, 48px height, rounded-lg)
- Divider with "or" text (only when dev password login enabled)
- Password input (only when `NEXT_PUBLIC_ENABLE_DEV_PASSWORD_LOGIN=true`)
- "Sign in with Password" button (ghost variant — outline, no fill)
- Footer: subtle muted text

**States**:
- Loading: Button shows spinner, disabled
- Success: "Check your email for the magic link" message in accent-light bg
- Error: Red error message below input

---

### 3.2 Auth Callback (`/auth/callback`)

**Layout**: Centered spinner with "Signing you in..." text. Processes the `?code=` param, exchanges for session, redirects to `/rooms`.

---

### 3.3 Rooms List (`/rooms`)

**Layout**: Sidebar (room list) + main area showing selected room's workspace. This is the primary landing page after login.

**Sidebar**:
- Header: "Pantheon" wordmark + hamburger toggle (mobile) + "New Room" button (accent, small)
- Room list: Each room card shows:
  - Room name (14px, bold)
  - Mode badge pill: Solo Chat (teal), Team Discussion (orange), Auto Best Answer (purple) — 10px text, uppercase, letter-spacing
  - Goal preview (truncated, 12px, muted)
  - Delete button (appears on hover, trash icon, red on hover)
- Active room: `--bg-elevated` background, left 3px accent border
- "My Agents" link at bottom → navigates to `/agents`
- "Billing" link → `/billing`
- User email + logout at very bottom

**Create Room Modal**:
- Room name input (required)
- Room goal textarea (optional, hint: "Required for Auto Best Answer mode")
- Mode selector: 3 radio cards (Solo Chat, Team Discussion, Auto Best Answer) with descriptions and color-coded icons
- "Create Room" button (accent)

---

### 3.4 Room Workspace (`/rooms/[roomId]`)

This is the **main interaction screen**. The most complex page.

**Header Bar** (fixed top, `--bg-surface` bg, bottom border):
- Room name (editable on click? future feature)
- Mode dropdown selector (shows current mode as colored badge, dropdown to switch)
- Room goal display (small, muted, truncated with tooltip for full text)
- Agent count badge

**Room Panels** (in sidebar or collapsible panels):

**Agent Panel**:
- "Agents" header with "Assign Agent" button
- List of assigned agents, each showing:
  - Agent name (bold)
  - `@agent_key` (muted, monospace)
  - Model alias badge
  - Tool icons (🔍 for search, 📄 for file_read)
  - Position number (drag handle for reorder — future)
  - Remove button (X, appears on hover)
- "Assign Agent" modal: dropdown of user's agents (not already assigned), position input

**Session Panel**:
- "Sessions" header with "New Session" button (+ icon)
- Session list: each shows truncated session ID (first 8 chars), creation date
- Active session highlighted with `--bg-elevated`
- Delete session (trash icon, appears on hover)

**File Panel**:
- "Files" header with upload button (📎)
- File list: filename, size, parse status dot (green/orange/red)
- Upload: triggers file picker (restricted to `.txt, .md, .csv, .pdf, .docx, .xlsx, .xls`, max 1MB)
- Upload goes to room-level endpoint: `POST /rooms/{roomId}/files`

**Chat Area** (center, scrollable):

**Message Rendering**:
- **User messages**: Right-aligned, `--bg-user-message` background (cream-yellow), rounded-2xl (18px radius), max-width 85%, padding 12px 16px. Shows the raw user text.
- **Agent responses**: Left-aligned, no background bubble, full content width (up to 768px). Agent name label above: uppercase, 11px, bold, colored per mode accent. Content below in regular 16px body text. Supports markdown rendering (headers, lists, code blocks, bold, italic).
- **Manager routing card** (orchestrator only): System card with `--bg-surface` background, left 3px `--mode-auto` border, padding 12px 16px. Shows: "Manager Routing (Round N) — Selected: @agent1, @agent2". Italic, `--text-secondary` color.
- **Manager evaluation card**: Same style. "Manager Evaluation — Decision: Continue / End specialist rounds. Synthesizing."
- **Manager synthesis**: Separated by a subtle `<hr>` divider. Label: "SYNTHESIS" in uppercase muted text. Content flows normally.
- **Tool invocation indicator**: Inline within agent response. Small muted tag: "🔍 Searching: {query}..." while pending, "🔍 Search complete" when done. For file_read: "📄 Reading: {filename}..."
- **Error messages**: Red text in a `--error` bg-opacity-10 container, red left border.
- **Turn boundaries**: 24px vertical gap between turns. Within a turn, 8px gap between agent responses.

**Input Bar** (fixed bottom of chat area):
- Pill-shaped container: `--bg-input` bg, 1px `--border` border, 24px border-radius, `--border-focus` ring on focus
- Textarea (auto-grows, min 1 row, max 6 rows, 16px font — prevents iOS zoom)
- In Solo Chat mode: placeholder "Tag an agent with @key to chat..."
- In Team Discussion: placeholder "Message all agents..."
- In Auto Best Answer: placeholder "Ask your council anything..."
- 📎 button (left of input or inside): triggers file upload (to session endpoint if session selected, room endpoint otherwise)
- Send button (right): circular, 36px, `--accent` bg, white arrow icon. Disabled + dimmed when input empty. Scale animation on press.
- `@` autocomplete: When user types `@`, show dropdown of assigned agent keys above input. Filter as user types. Click to insert `@agentkey `.

**SSE Streaming UX**:
- When turn is submitted: disable input, show typing indicator
- On `agent_start`: Create new agent message block with agent name label. Show blinking cursor.
- On `chunk`: Append text character by character. Auto-scroll to bottom.
- On `agent_end`: Remove cursor. Message complete.
- On `manager_think` (routing): Insert routing card before next agent responses.
- On `manager_think` (evaluation): Insert evaluation card.
- On `tool_start`: Show inline tool indicator in current agent's message.
- On `tool_end`: Update indicator to "complete".
- On `error`: Show error message block.
- On `done`: Re-enable input. Store turn metadata. Check `low_balance` — if true, show yellow warning banner.

Refer to `docs/ui_ux_developer_instructions.md` Section 9 (SSE Streaming Protocol) and Section 16 (test_ui.html Reference Implementation) for the complete event schema and JavaScript implementation patterns.

---

### 3.5 Agents Page (`/agents`)

**Layout**: Full-page list (no sidebar needed, or reuse rooms sidebar with "Agents" tab active).

**Agent List**:
- Grid of agent cards (responsive: 1 col mobile, 2 col tablet, 3 col desktop)
- Each card shows:
  - Agent name (16px, bold)
  - `@agent_key` in monospace, muted
  - Model alias badge (small pill, muted bg)
  - Role prompt preview (2 lines, truncated with ellipsis)
  - Tool permission icons: 🔍 (search), 📄 (file_read)
  - Edit button (pencil icon) → opens edit modal
  - Delete button (trash icon, red on hover) → confirmation dialog

**Create Agent Button**: Top-right, accent gold. Opens create modal.

**Create/Edit Agent Modal**:
- Agent Key input (1-64 chars, alphanumeric + underscore, hint: "Used for @mentions")
- Name input (1-120 chars)
- Model selector dropdown: Free, Llama, Qwen, DeepSeek, GPT OSS, Premium — show tier labels
- Role Prompt textarea (multiline, min 3 rows, hint: "Define the agent's personality, expertise, and instructions")
- Tool permissions: Two checkboxes — "Web Search" and "File Read"
- Save / Create button (accent)

---

### 3.6 Standalone Agent Chat

Users can chat 1-on-1 with an agent outside any room:
- Accessible from agent card → "Chat" button
- Creates standalone session via `POST /agents/{agentId}/sessions`
- Same chat UI as room workspace but without mode switching, agent panel, or multi-agent features
- Single agent responds directly

---

### 3.7 Billing Page (`/billing`)

**Layout**: Centered content (max-width 800px), clean and simple.

**Sections**:

1. **Balance Card** (prominent, top):
   - Large number: current credit balance from `GET /users/me/wallet`
   - "Credits" label below
   - Gold accent border or background tint

2. **Top Up Section**:
   - Amount input (number, min $1, max $500, step $0.01)
   - Quick-select buttons: $5, $10, $25, $50
   - "Shows approximately X credits" calculated preview (amount_usd / 0.03)
   - "Add Credits" button (accent gold) → calls `POST /users/me/wallet/top-up`
   - Stripe Elements card input appears after clicking (use `@stripe/react-stripe-js`)
   - Confirm payment → poll wallet endpoint for updated balance

3. **Usage History Table**:
   - `GET /users/me/usage` — paginated
   - Columns: Date, Model, Credits Burned
   - Sortable by date (newest first)

4. **Transaction History Table**:
   - `GET /users/me/transactions` — paginated
   - Columns: Date, Type (grant/debit/refund), Amount (+/-), Note
   - Color-coded: green for grants, red for debits

---

### 3.8 Admin Dashboard (`/admin`)

Protected route — only accessible when user_id is in `ADMIN_USER_IDS`. API returns 403 for non-admins. Show "Access Denied" page if 403.

**Sub-navigation tabs**: Pricing | Usage | Users | Settings

#### 3.8.1 Pricing Tab
- Table: Model Alias | Display Name | Multiplier | Pricing Version
- Multiplier is an editable number input (0.01–100.0)
- Save button per row or bulk save
- `GET /admin/pricing` → `PATCH /admin/pricing/{model_alias}`

#### 3.8.2 Usage Tab
- **Filters bar**: Date range picker, User ID input, Model dropdown, Bucket selector (Day/Week/Month)
- **Summary cards** (row of 3): Total Credits Burned, Total LLM Calls, Total Output Tokens
- **Bar chart**: Daily/weekly/monthly usage over time (use a lightweight chart lib — recharts or chart.js)
- **Pie chart**: Credit breakdown by model
- **Per-user table**: Sortable, paginated — User ID, Model, Total Tokens, Credits Burned
- `GET /admin/usage/summary` + `GET /admin/analytics/usage`

#### 3.8.3 Users Tab
- **Active Users cards**: Active Users count, New Users count, with period selector (Day/Week/Month)
- `GET /admin/analytics/active-users`
- **Wallet Lookup**: Search by User ID → shows balance + last 10 transactions
- **Grant Credits form**: Amount input (0–10,000) + Note textarea + "Grant" button
- `GET /admin/wallets/{user_id}` + `POST /admin/wallets/{user_id}/grant`

#### 3.8.4 Settings Tab
- Credit enforcement toggle switch (on/off)
- Current source indicator: "Config default" or "Admin override"
- Low balance threshold display
- Active pricing version
- `GET /admin/settings` + `PATCH /admin/settings/enforcement`

---

### 3.9 User Profile / Settings

Simple page:
- Display email and user ID
- Logout button
- Theme toggle (light/dark)

---

## 4. Component Specifications

### 4.1 `<Sidebar />`
- Width: 260px desktop, full-screen overlay mobile
- Background: `--bg-sidebar`
- Contains: RoomList, SessionList, AgentPanel, FilePanel, navigation links
- Collapse button (chevron icon) on desktop, hamburger on mobile
- Props: `isOpen`, `onToggle`, `activeRoomId`

### 4.2 `<ChatMessage />`
- Variants: `user`, `agent`, `system`, `error`
- User variant: right-aligned, cream-yellow bg, rounded-2xl
- Agent variant: left-aligned, no bg, agent name label above (colored, uppercase, 11px)
- System variant: centered, italic, muted
- Error variant: red bg tint, red left border
- Supports markdown rendering (use `react-markdown` or `marked`)
- Props: `role`, `agentName?`, `content`, `timestamp`

### 4.3 `<ManagerCard />`
- Used for orchestrator routing and evaluation events
- Background: `--bg-surface`, left 3px border in `--mode-auto` color
- Variants: `routing` (shows selected agents), `evaluation` (shows decision)
- Props: `type: 'routing' | 'evaluation'`, `round?`, `agents?`, `decision?`

### 4.4 `<ChatInput />`
- Pill-shaped container (24px border-radius)
- Auto-growing textarea (1–6 rows)
- Attach button (📎), Send button (circular, gold)
- `@` autocomplete dropdown above input
- Loading state: disabled with spinner in send button
- Props: `onSubmit`, `agents` (for autocomplete), `mode`, `disabled`

### 4.5 `<ModeBadge />`
- Colored pill: teal (Solo Chat), orange (Team Discussion), purple (Auto Best Answer)
- Text: mode display name, 10px, uppercase, letter-spacing 0.8px
- Props: `mode: 'manual' | 'roundtable' | 'orchestrator'`

### 4.6 `<ModeSelector />`
- Dropdown showing current mode as `<ModeBadge />`
- Options: Solo Chat, Team Discussion, Auto Best Answer — each with 1-line description
- On change: `PATCH /rooms/{roomId}/mode`
- Props: `currentMode`, `onChange`

### 4.7 `<AgentCard />`
- Shows: name, @key, model badge, tool icons, role prompt preview
- Actions: Edit (pencil), Delete (trash), Chat (message icon)
- Props: `agent: AgentRead`

### 4.8 `<FileStatusDot />`
- 8px circle: green (completed), orange (pending), red (failed)
- Props: `status: 'pending' | 'completed' | 'failed'`

### 4.9 `<CreditBalance />`
- Large number display with "Credits" label
- Gold accent border/tint
- Low balance warning state (yellow banner below)
- Props: `balance: string`, `lowBalance: boolean`

### 4.10 `<ConfirmDialog />`
- Modal with title, description, Cancel + Confirm buttons
- Confirm button: red for destructive actions, accent for positive
- Props: `title`, `description`, `onConfirm`, `onCancel`, `variant`

### 4.11 `<SkeletonLoader />`
- Pulse animation (opacity 0.5 → 1, 1.5s)
- Variants: line (for text), card (for agent/room cards), message (for chat messages)

### 4.12 `<LowBalanceBanner />`
- Sticky banner at top of chat area
- Yellow/gold background tint
- Text: "Your credit balance is running low. Top up to continue using Pantheon."
- "Top Up" button linking to `/billing`
- Dismissible (X button)

---

## 5. Build Instructions for Stitch

### Project Setup
- Framework: Next.js 14 (App Router)
- Language: TypeScript (strict mode)
- Styling: Tailwind CSS 3.4 with CSS custom properties for theme tokens
- State: Zustand v5 for global state, TanStack React Query v5 for server state
- Auth: `@supabase/ssr` + `@supabase/supabase-js`
- Icons: `lucide-react`
- Markdown: `react-markdown` with `remark-gfm`
- Payments: `@stripe/react-stripe-js` + `@stripe/stripe-js`
- Charts (admin): `recharts` (lightweight, React-native)

### Environment Variables
```
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=<supabase_url>
NEXT_PUBLIC_SUPABASE_ANON_KEY=<supabase_anon_key>
NEXT_PUBLIC_ENABLE_DEV_PASSWORD_LOGIN=true
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=<stripe_pk>
```

### Directory Structure
```
src/
├── app/
│   ├── layout.tsx              # Root layout, providers, theme
│   ├── page.tsx                # Redirect to /rooms or /auth/login
│   ├── auth/
│   │   ├── login/page.tsx      # Login page
│   │   └── callback/page.tsx   # Auth callback handler
│   ├── rooms/
│   │   ├── page.tsx            # Room list (redirects to workspace of first room)
│   │   └── [roomId]/page.tsx   # Room workspace (main chat view)
│   ├── agents/page.tsx         # Agent management
│   ├── billing/page.tsx        # Billing & wallet
│   └── admin/
│       ├── layout.tsx          # Admin guard (check 403)
│       └── page.tsx            # Admin dashboard with tabs
├── components/
│   ├── layout/
│   │   ├── Sidebar.tsx
│   │   └── Header.tsx
│   ├── chat/
│   │   ├── ChatArea.tsx        # Scrollable message list
│   │   ├── ChatMessage.tsx     # User/agent/system message
│   │   ├── ChatInput.tsx       # Pill-shaped input with autocomplete
│   │   ├── ManagerCard.tsx     # Orchestrator routing/evaluation card
│   │   ├── ToolIndicator.tsx   # Inline tool invocation display
│   │   └── StreamHandler.tsx   # SSE stream processing logic
│   ├── agents/
│   │   ├── AgentCard.tsx
│   │   ├── AgentForm.tsx       # Create/edit modal form
│   │   └── AgentPanel.tsx      # Sidebar agent list for rooms
│   ├── rooms/
│   │   ├── RoomCard.tsx
│   │   ├── RoomForm.tsx        # Create room modal
│   │   ├── ModeSelector.tsx
│   │   ├── ModeBadge.tsx
│   │   └── SessionPanel.tsx    # Session list in sidebar
│   ├── billing/
│   │   ├── CreditBalance.tsx
│   │   ├── TopUpForm.tsx
│   │   └── TransactionTable.tsx
│   ├── admin/
│   │   ├── PricingTable.tsx
│   │   ├── UsageDashboard.tsx
│   │   ├── ActiveUsersCard.tsx
│   │   ├── WalletLookup.tsx
│   │   └── SettingsPanel.tsx
│   └── ui/
│       ├── Button.tsx          # CVA button variants
│       ├── Input.tsx
│       ├── Modal.tsx
│       ├── ConfirmDialog.tsx
│       ├── SkeletonLoader.tsx
│       ├── FileStatusDot.tsx
│       ├── LowBalanceBanner.tsx
│       └── Badge.tsx
├── lib/
│   ├── api.ts                  # Base fetch wrapper with auth headers
│   ├── supabase/
│   │   ├── client.ts           # Browser Supabase client
│   │   ├── server.ts           # Server Supabase client
│   │   └── middleware.ts       # Auth middleware
│   ├── stripe.ts               # Stripe client setup
│   └── constants.ts            # Model aliases, mode labels, etc.
├── hooks/
│   ├── useAgents.ts            # React Query hooks for agents CRUD
│   ├── useRooms.ts             # React Query hooks for rooms CRUD
│   ├── useSessions.ts          # React Query hooks for sessions
│   ├── useMessages.ts          # React Query hooks for messages
│   ├── useStream.ts            # SSE streaming hook
│   ├── useWallet.ts            # Wallet balance + transactions
│   └── useAuth.ts              # Auth state
├── stores/
│   └── chatStore.ts            # Zustand: active room, session, streaming state
└── styles/
    └── globals.css             # CSS custom properties (theme tokens)
```

### Progressive Web App (PWA)

Make this app installable on mobile devices:

1. Add `next-pwa` package
2. Create `public/manifest.json`:
```json
{
  "name": "Pantheon",
  "short_name": "Pantheon",
  "description": "AI Multi-Agent Orchestration Platform",
  "start_url": "/rooms",
  "display": "standalone",
  "background_color": "#FFFFFF",
  "theme_color": "#D4A017",
  "icons": [
    { "src": "/icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/icon-512.png", "sizes": "512x512", "type": "image/png" }
  ]
}
```
3. Register service worker for offline shell caching
4. Add meta tags in root layout:
```html
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no" />
<meta name="apple-mobile-web-app-capable" content="yes" />
<meta name="apple-mobile-web-app-status-bar-style" content="default" />
<link rel="manifest" href="/manifest.json" />
<meta name="theme-color" content="#D4A017" />
```

### Mobile Responsiveness Requirements

- **All pages must work on 320px width and up**
- Sidebar collapses to hamburger menu below 768px
- Chat input remains full-width and accessible on all screen sizes
- Modals become full-screen sheets on mobile (slide up from bottom)
- Agent cards stack to single column on mobile
- Admin dashboard tables become horizontally scrollable cards on mobile
- Touch targets minimum 44x44px (Apple HIG)
- No horizontal scroll on any page at any breakpoint
- Font size ≥ 16px on inputs (prevents iOS auto-zoom)

### Key Implementation Notes

1. **SSE Streaming**: Use `fetch()` + `ReadableStream` (NOT `EventSource`). Split on `/\r?\n/` for cross-platform line ending support. See `docs/ui_ux_developer_instructions.md` Section 9 and Section 16 for complete implementation reference.

2. **File Upload**: Use `FormData` (NOT `JSON`). Field name: `file`. Allowed: `.txt, .md, .csv, .pdf, .docx, .xlsx, .xls`. Max 1MB.

3. **@mention Autocomplete**: When user types `@` in chat input, show filtered dropdown of assigned agent keys. Insert `@agentkey ` on selection. Required in Solo Chat mode.

4. **Mode Switching**: `PATCH /rooms/{roomId}/mode` with `{ mode: "roundtable" }`. Optimistic update with revert on error.

5. **Error Handling**: Map HTTP status codes to user-friendly messages. 401 → redirect to login. 402 → show top-up prompt. 422 → show validation error from response body. 429 → show retry countdown using `Retry-After` header.

6. **Low Balance Warning**: Check `low_balance` field in turn `done` event. If `true`, show `<LowBalanceBanner />`.

7. **Auth Flow**: Supabase session stored in cookies. Middleware refreshes token. All API calls include `Authorization: Bearer {token}`. For local dev, `Bearer dev-override` bypasses auth.

8. **React Query Configuration**: Stale time 30s for lists, 60s for static data (pricing, settings). Invalidate on mutations. Optimistic updates for mode changes and agent updates.

9. **`test_ui.html` as Reference**: The file at project root (`test_ui.html`, served at `/test-console`) implements every feature in vanilla JS. Study it for correct API call sequences, SSE event handling, and orchestrator rendering. See `docs/ui_ux_developer_instructions.md` Section 16 for line-by-line guide.

---

Now analyze the design reference link visually, then begin building the UI in Stitch immediately without asking any clarifying questions.
