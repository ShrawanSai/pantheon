# Pantheon - UI/UX Developer Instructions

> **Version:** 1.0 | **Last updated:** 2026-02-28
> **Audience:** Frontend / UI/UX developers building the production web application

---

## Table of Contents

1. [What is Pantheon?](#1-what-is-pantheon)
2. [Design Vision & Vibes](#2-design-vision--vibes)
3. [What It Solves](#3-what-it-solves)
4. [Architecture Overview](#4-architecture-overview)
5. [Supported LLM Models](#5-supported-llm-models)
6. [Authentication](#6-authentication)
7. [Core Features & Screens](#7-core-features--screens)
8. [Complete API Reference](#8-complete-api-reference)
9. [SSE Streaming Protocol](#9-sse-streaming-protocol)
10. [Room Modes & Interaction Design](#10-room-modes--interaction-design)
11. [Billing, Credits & Wallet](#11-billing-credits--wallet)
12. [Admin Dashboard](#12-admin-dashboard)
13. [File Uploads](#13-file-uploads)
14. [Current Frontend State](#14-current-frontend-state)
15. [Design System & Tokens](#15-design-system--tokens)
16. [test_ui.html Reference Implementation](#16-test_uihtml-reference-implementation)
17. [User Stories & Expected Behaviors](#17-user-stories--expected-behaviors)

---

## 1. What is Pantheon?

Pantheon is an **AI multi-agent orchestration platform**. Think of it as a workspace where users create custom AI agents (each with their own personality, expertise, and tools), assign them to collaborative "rooms," and run conversations where multiple agents work together to answer questions.

The core concept: **a user builds a council of AI specialists, then orchestrates them like a team.**

- A **Room** is a workspace. It has a mode that controls how agents interact.
- An **Agent** is a custom AI persona. It has a name, a system prompt (role), a model, and optional tool access (web search, file reading).
- A **Session** is a conversation thread within a room (or with a standalone agent).
- A **Turn** is one user message + the agent response(s) it triggers.

Example use case: A product manager creates a room called "Strategy Council" with three agents: a Market Analyst, a Technical Architect, and a Risk Assessor. In orchestrator mode, the platform's routing manager selects which specialists should respond to each question, gives them tailored instructions, collects their answers, and synthesizes a unified recommendation.

---

## 2. Design Vision & Vibes

### Aesthetic

**Dark-first. Professional. Command-center energy.** This is a power tool for people who take AI seriously, not a chat toy. Think Bloomberg Terminal meets Linear meets a high-end recording studio's mixing board.

- **Primary palette:** Near-black backgrounds (`#09090b`), dark surface grays (`#18181b`), elevated grays (`#27272a`)
- **Accent:** Deep purple (`#7c3aed`) — signals intelligence, precision, premium
- **Text:** Off-white (`#fafafa`) primary, muted gray (`#71717a`) for secondary
- **Borders:** Subtle dark lines (`#3f3f46`) — structure without clutter
- **No light mode.** Dark only. This is intentional.

### Feel

- **Responsive and alive.** Streaming responses should feel like watching someone think in real-time. Chunks appear character by character. Manager routing decisions appear as elegant status cards between agent responses.
- **Dense but not cluttered.** Show a lot of information (agents, rooms, sessions, files, chat, mode controls) but with clear hierarchy and whitespace.
- **Confidence-inspiring.** When the orchestrator routes to specialists, the user should feel like they're watching a well-coordinated team. Show which agents were selected, what instructions they received, and when the manager decides to continue or synthesize.
- **Minimal chrome.** No unnecessary decorations. Every pixel earns its place.

### Reference points

- Linear (task management UI density and polish)
- Raycast (dark theme, keyboard-first interaction)
- Vercel Dashboard (clean, professional, dark)
- Cursor IDE (agent interaction patterns)

---

## 3. What It Solves

### The Problem

Current AI chat interfaces are **single-agent, single-perspective**. You get one model, one system prompt, one personality. If you want multiple viewpoints, you copy-paste between tabs. If you want agents to build on each other's work, you manually relay context. There's no structure for multi-agent collaboration.

### How Pantheon Solves It

1. **Custom agents with roles:** Users define specialists with unique system prompts, models, and tools. A "Legal Analyst" agent has different instructions than a "Creative Director" agent.

2. **Three collaboration modes:**
   - **Manual/Tag (Solo Chat):** Direct conversation with a specific agent using `@agentkey`. One-on-one.
   - **Roundtable (Team Discussion):** All agents in the room respond sequentially. Each agent sees what the previous agents said. Like a meeting where everyone speaks in turn.
   - **Orchestrator (Auto Best Answer):** An AI manager reads the user's question, decides which specialists should respond, gives them targeted instructions, evaluates if another round is needed, and produces a synthesized final answer.

3. **Persistent context:** Sessions maintain conversation history with automatic summarization when context limits are approached. Agents remember their tool call history across turns.

4. **Tool integration:** Agents can search the web and read uploaded files, grounding their responses in real data.

5. **Credit-based billing:** Usage is metered per LLM call with model-specific pricing multipliers, wallet management, and Stripe top-ups.

---

## 4. Architecture Overview

```
Frontend (Next.js 14)          API (FastAPI/Python)           LLM Provider
      |                              |                            |
      |--- REST + SSE ------------->  |--- OpenRouter API ------> |
      |                              |                            |
      |                        [Supabase Postgres]                |
      |                        [Supabase Auth]                    |
      |                        [Supabase Storage]                 |
```

- **Frontend:** Next.js 14, TypeScript, Tailwind CSS, TanStack React Query v5, Zustand, Supabase Auth
- **Backend:** Python 3.12, FastAPI, SQLAlchemy (async), Supabase Postgres
- **LLM Gateway:** OpenRouter (OpenAI-compatible API) routing to multiple model providers
- **Auth:** Supabase Auth (magic link + dev password for localhost)
- **File Storage:** Supabase Storage (S3-compatible)
- **Payments:** Stripe (payment intents + webhooks)
- **Test Frontend:** `test_ui.html` — a self-contained vanilla HTML/JS app served at `GET /test-console` that implements every feature. **This file is your primary implementation reference.**

---

## 5. Supported LLM Models

These are the model aliases users select when creating agents. The backend maps them to actual provider model IDs via OpenRouter:

| Alias | Display Name | Model ID | Tier | Notes |
|-------|-------------|----------|------|-------|
| `free` | Free | Mistral Small 3.1 24B | Free | No cost, good for testing |
| `llama` | Llama | Meta Llama 4 Scout | Economy | Budget-friendly |
| `qwen` | Qwen | Qwen3 235B | Economy | Strong multilingual |
| `deepseek` | DeepSeek | Gemini 2.5 Flash | Standard | Default for manager/summarizer |
| `gpt_oss` | GPT OSS | OpenAI GPT-OSS 120B | Advanced | Higher capability |
| `premium` | Premium | Gemini 2.5 Pro | Premium | Highest quality, highest cost |

The model selector dropdown should present these as user-friendly names. The `model_alias` string is what gets sent to the API.

---

## 6. Authentication

### Flow

1. User enters email on login page
2. Two methods available:
   - **Magic Link (production):** Supabase sends OTP email → user clicks link → redirected to `/auth/callback?code=...` → code exchanged for session → redirect to `/rooms`
   - **Password login (dev/localhost only):** Direct sign-in with email + password. Only shown when `NEXT_PUBLIC_ENABLE_DEV_PASSWORD_LOGIN=true`
3. Supabase session stored in cookies, refreshed via middleware
4. JWT access token automatically injected in all API calls via `Authorization: Bearer {token}`

### Auth Middleware

- All routes except `/`, `/auth/*` are protected
- Unauthenticated users redirected to `/auth/login?next={currentPath}`
- Authenticated users on public paths redirected to `/rooms`

### API Auth Header

All API calls require:
```
Authorization: Bearer {supabase_jwt_token}
```

For local development/testing, the backend accepts `Bearer dev-override` as a bypass token (non-production environments only).

### Key Endpoint

- `GET /api/v1/auth/me` — Returns `{ user_id, email }` for the authenticated user

---

## 7. Core Features & Screens

### 7.1 Agent Management

**Route:** `/agents`

Agents are the AI specialists users configure. Each agent has:

| Field | Type | Description |
|-------|------|-------------|
| `agent_key` | string (1-64 chars) | Unique identifier for @mentions (e.g., `writer`, `analyst`) |
| `name` | string (1-120 chars) | Display name (e.g., "Tony Stark", "Legal Advisor") |
| `model_alias` | string | One of: `free`, `llama`, `qwen`, `deepseek`, `gpt_oss`, `premium` |
| `role_prompt` | text | System prompt defining the agent's personality and expertise |
| `tool_permissions` | string[] | Which tools the agent can use: `["search"]`, `["file_read"]`, or both |

**CRUD Operations:**
- Create agent (form with all fields above)
- List agents (paginated, shows key, name, model, tools)
- Update agent (partial update of any field)
- Delete agent (soft delete — can recreate same `agent_key` after deletion)

**UI Notes:**
- Model selector should be a dropdown with the 6 supported aliases
- Tool permissions should be checkboxes: "Web Search" and "File Read"
- Show the `@agent_key` prominently — users need to remember these for @mentions in manual/tag mode
- After deletion, the key becomes available for reuse immediately

---

### 7.2 Room Management

**Route:** `/rooms`

Rooms are collaborative workspaces where agents are assigned and conversations happen.

| Field | Type | Description |
|-------|------|-------------|
| `name` | string (1-200 chars) | Room name |
| `goal` | text (optional) | Room objective — **required for orchestrator mode** |
| `current_mode` | enum | `manual`, `roundtable`, or `orchestrator` |

**Mode Labels for UI (user-friendly names):**
- `manual` → "Solo Chat"
- `roundtable` → "Team Discussion"
- `orchestrator` → "Auto Best Answer"

**CRUD + Operations:**
- Create room (name, optional goal, mode selection)
- List rooms (show name, mode badge, goal preview)
- Delete room (soft delete)
- **Change mode** — `PATCH /rooms/{roomId}/mode` with `{ mode: "roundtable" }`
- **Assign agent to room** — `POST /rooms/{roomId}/agents` with `{ agent_id, position }`
- **List room agents** — `GET /rooms/{roomId}/agents` (shows agent details + position)
- **Unassign agent** — `DELETE /rooms/{roomId}/agents/{agentId}`

**UI Notes:**
- Mode badge should be color-coded: Solo Chat (teal), Team Discussion (orange), Auto Best Answer (purple)
- Mode can be switched at any time via a dropdown in the room header
- Room goal is important for orchestrator mode — the manager uses it for context
- Agent assignment should show position (speaking order) with ability to reorder
- Room cards in the list should link to the workspace view (`/rooms/[roomId]`)

---

### 7.3 Room Workspace (Chat View)

**Route:** `/rooms/[roomId]`

This is the main interaction screen. It should contain:

1. **Header:** Room name, mode selector dropdown, room goal display
2. **Agent panel:** List of assigned agents with their roles (collapsible sidebar or panel)
3. **Session management:** Session list, create new session, switch sessions
4. **File panel:** Uploaded files with parse status indicators
5. **Chat area:** Message history with turn boundaries, agent labels, manager routing cards
6. **Input area:** Message input, file upload button, send button, optional model override

**Message Types to Render:**

| Type | Source | Rendering |
|------|--------|-----------|
| User message | The human | Right-aligned or distinct style, shows the raw text |
| Agent response | An AI agent | Left-aligned, prefixed with agent name label (uppercase, colored) |
| Manager routing | Orchestrator manager | System card: "Manager Routing (Round N) — Selected: @agent1, @agent2" |
| Manager evaluation | Orchestrator manager | System card: "Manager Evaluation — Decision: Continue / Synthesize" |
| Manager synthesis | Orchestrator manager | Distinct block: "Manager Synthesis:" followed by consolidated answer |
| System message | Platform | Italic, dimmed — errors, status updates |

**Chat Input Behavior:**
- In manual mode: User MUST include `@agentkey` in their message. If they forget, API returns 422
- In roundtable mode: All assigned agents respond in sequence
- In orchestrator mode: Manager routes automatically, user just types normally
- Multiple @mentions in manual mode auto-escalates to roundtable behavior

---

### 7.4 Standalone Agent Sessions

Users can also chat 1-on-1 with an agent outside of any room context:

- `POST /api/v1/agents/{agentId}/sessions` — Create standalone session
- `GET /api/v1/agents/{agentId}/sessions` — List standalone sessions

Standalone sessions have `room_id=null` and `mode=standalone`. The agent responds directly without room context or multi-agent collaboration.

---

### 7.5 Billing & Wallet Page

**Route:** `/billing`

**Currently a stub — needs full implementation.**

This page should show:

1. **Current balance:** Credit balance from `GET /users/me/wallet`
2. **Top-up button:** Opens Stripe Checkout flow
   - User enters amount (min $1.00, max $500.00)
   - `POST /users/me/wallet/top-up` returns Stripe `client_secret`
   - Use Stripe.js Elements to complete payment
   - Webhook auto-grants credits on successful payment
3. **Usage history:** `GET /users/me/usage` — list of LLM calls with model, credits burned, date
4. **Transaction history:** `GET /users/me/transactions` — all debits/grants/refunds with amounts

**Credit System Basics:**
- Credits are charged per LLM call based on token usage and model multiplier
- Formula: `OE_tokens = (input_fresh * 0.35) + (input_cached * 0.10) + output_tokens`
- `credits = OE_tokens * model_multiplier / 10,000`
- When enforcement is enabled and balance hits 0, turns are blocked with HTTP 402
- Turn responses include `balance_after` and `low_balance` fields — use these to show balance warnings

**Low Balance Warning:**
When `low_balance: true` appears in a turn response, show a prominent warning banner: "Your credit balance is running low. Top up to continue using Pantheon."

---

### 7.6 Admin Dashboard

**Route:** `/admin` (protected — only accessible to users whose IDs are in `ADMIN_USER_IDS` env var)

**Not yet built — needs full implementation.**

The admin dashboard provides platform-wide visibility and control:

#### Pricing Management
- `GET /admin/pricing` — View all model pricing multipliers
- `PATCH /admin/pricing/{model_alias}` — Update a model's multiplier (0.0-100.0)
- Display as a table: Model Alias | Current Multiplier | Pricing Version

#### Usage Analytics
- `GET /admin/usage/summary` — System-wide usage stats
  - Query params: `user_id`, `model_alias`, `from_date`, `to_date`, `bucket` (day/week/month)
  - Response: total credits burned, total LLM calls, breakdown per model, daily time series
  - **Visualize as:** Summary cards + bar chart of daily usage + pie chart of model breakdown

- `GET /admin/analytics/usage` — Per-user detailed analytics
  - Query params: `start_date`, `end_date`, `limit`, `offset`
  - Response: Rows of user_id + model_alias + total tokens + credits burned
  - **Visualize as:** Sortable table, paginated

- `GET /admin/analytics/active-users` — Active user counts
  - Query params: `window` (day/week/month), `as_of` (date)
  - Response: `active_users` count, `new_users` count
  - **Visualize as:** Metric cards with period selector

#### System Settings
- `GET /admin/settings` — Current enforcement state, pricing version, low balance threshold
- `PATCH /admin/settings/enforcement` — Toggle credit enforcement on/off (in-memory override)
- `DELETE /admin/settings/enforcement` — Clear override, revert to config default
- Display as: Toggle switch for enforcement + status indicator showing "config" vs "override"

#### Wallet Management
- `GET /admin/wallets/{user_id}` — View any user's balance + last 10 transactions
- `POST /admin/wallets/{user_id}/grant` — Grant credits to a user (amount: 0-10,000, optional note)
- `POST /admin/users/{user_id}/wallet/grant` — Alternative grant endpoint
- **UI:** Search by user_id → show balance + transaction list + "Grant Credits" button with amount + note fields

---

### 7.7 User Profile / Settings

**Not yet built.** Consider adding:
- View account email and user ID
- View/manage API sessions
- Logout

---

## 8. Complete API Reference

### Base URL
```
{NEXT_PUBLIC_API_BASE_URL}/api/v1
```
Default: `http://localhost:8000/api/v1`

All endpoints require `Authorization: Bearer {token}` unless noted otherwise.

---

### Health

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | No | Returns `{ status: "ok" }` |
| GET | `/graph-check` | No | Returns `{ engine_import_ok: bool }` |

---

### Auth

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/auth/me` | Yes | Returns `{ user_id, email }` |

---

### Agents

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/agents` | Yes | Create agent |
| GET | `/agents` | Yes | List agents (query: `limit`, `offset`) |
| GET | `/agents/{agent_id}` | Yes | Get agent |
| PATCH | `/agents/{agent_id}` | Yes | Update agent (partial) |
| DELETE | `/agents/{agent_id}` | Yes | Delete agent (soft) |

**Create/Update Body:**
```json
{
  "agent_key": "analyst",
  "name": "Market Analyst",
  "model_alias": "deepseek",
  "role_prompt": "You are a senior market analyst...",
  "tool_permissions": ["search", "file_read"]
}
```

**Response shape (AgentRead):**
```json
{
  "id": "uuid",
  "owner_user_id": "uuid",
  "agent_key": "analyst",
  "name": "Market Analyst",
  "model_alias": "deepseek",
  "role_prompt": "You are a senior market analyst...",
  "tool_permissions": ["search", "file_read"],
  "created_at": "2026-02-28T...",
  "updated_at": "2026-02-28T..."
}
```

---

### Rooms

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/rooms` | Yes | Create room |
| GET | `/rooms` | Yes | List rooms |
| GET | `/rooms/{room_id}` | Yes | Get room |
| DELETE | `/rooms/{room_id}` | Yes | Delete room (soft) |
| PATCH | `/rooms/{room_id}/mode` | Yes | Change room mode |
| POST | `/rooms/{room_id}/agents` | Yes | Assign agent to room |
| GET | `/rooms/{room_id}/agents` | Yes | List room agents |
| DELETE | `/rooms/{room_id}/agents/{agent_id}` | Yes | Remove agent from room |

**Create Body:**
```json
{
  "name": "Strategy Council",
  "goal": "Evaluate go-to-market strategies",
  "current_mode": "orchestrator"
}
```

**Mode Update Body:**
```json
{ "mode": "roundtable" }
```

**Agent Assignment Body:**
```json
{ "agent_id": "uuid", "position": 1 }
```

**Room Agent Response (RoomAgentRead):**
```json
{
  "id": "uuid",
  "room_id": "uuid",
  "agent_id": "uuid",
  "agent": { /* full AgentRead */ },
  "position": 1,
  "created_at": "..."
}
```

---

### Sessions

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/rooms/{room_id}/sessions` | Yes | Create room session |
| GET | `/rooms/{room_id}/sessions` | Yes | List room sessions |
| DELETE | `/rooms/{room_id}/sessions/{session_id}` | Yes | Delete room session |
| POST | `/agents/{agent_id}/sessions` | Yes | Create standalone session |
| GET | `/agents/{agent_id}/sessions` | Yes | List standalone sessions |
| DELETE | `/agents/{agent_id}/sessions/{session_id}` | Yes | Delete standalone session |

**Session Response:**
```json
{
  "id": "uuid",
  "room_id": "uuid",
  "agent_id": null,
  "started_by_user_id": "uuid",
  "created_at": "...",
  "deleted_at": null
}
```

---

### Messages & Turns

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/sessions/{session_id}/messages` | Yes | Get messages (query: `limit`, `offset`) |
| GET | `/sessions/{session_id}/turns` | Yes | Get turn history (query: `limit`, `offset`) |
| POST | `/sessions/{session_id}/turns` | Yes | Submit turn (non-streaming) |
| POST | `/sessions/{session_id}/turns/stream` | Yes | Submit turn (SSE streaming) |

**Turn Request Body:**
```json
{
  "message": "@analyst What are the top 3 market risks?",
  "model_alias_override": null
}
```

**Turn Response (non-streaming):**
```json
{
  "id": "uuid",
  "session_id": "uuid",
  "turn_index": 3,
  "mode": "orchestrator",
  "user_input": "...",
  "assistant_output": "...",
  "status": "completed",
  "model_alias_used": "deepseek",
  "summary_triggered": false,
  "prune_triggered": false,
  "overflow_rejected": false,
  "balance_after": "25.50",
  "low_balance": false,
  "summary_used_fallback": false,
  "created_at": "..."
}
```

**Messages Response:**
```json
{
  "messages": [
    {
      "id": "uuid",
      "role": "user",
      "agent_name": null,
      "content": "What are the risks?",
      "turn_id": "uuid",
      "created_at": "..."
    },
    {
      "id": "uuid",
      "role": "assistant",
      "agent_name": "Market Analyst",
      "content": "Based on my analysis...",
      "turn_id": "uuid",
      "created_at": "..."
    }
  ],
  "total": 42
}
```

---

### Files

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/rooms/{room_id}/files` | Yes | Upload file to room (multipart/form-data) |
| GET | `/rooms/{room_id}/files` | Yes | List room files |
| POST | `/sessions/{session_id}/files` | Yes | Upload file to session |
| GET | `/sessions/{session_id}/files` | Yes | List session files |

**Upload:** Use `multipart/form-data` with field name `file`. Do NOT send `Content-Type: application/json`.

**Allowed extensions:** `.txt`, `.md`, `.csv`, `.pdf`, `.docx`, `.xlsx`, `.xls`

**Max file size:** 1 MB (configurable)

**File Response:**
```json
{
  "id": "uuid",
  "user_id": "uuid",
  "room_id": "uuid",
  "filename": "report.pdf",
  "storage_key": "...",
  "content_type": "application/pdf",
  "file_size": 524288,
  "parse_status": "completed",
  "parsed_text": "...",
  "error_message": null,
  "created_at": "..."
}
```

**Parse status values:**
- `pending` — still being processed (show orange indicator)
- `completed` — ready, agent can read it (show green indicator)
- `failed` — parse error (show red indicator)

---

### User Billing

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/users/me/wallet` | Yes | Get credit balance |
| POST | `/users/me/wallet/top-up` | Yes | Create Stripe payment intent |
| GET | `/users/me/usage` | Yes | Usage history (query: `limit`, `offset`) |
| GET | `/users/me/transactions` | Yes | Transaction history (query: `limit`, `offset`) |

**Wallet Response:**
```json
{ "user_id": "uuid", "balance": "33.50" }
```

**Top-up Request:**
```json
{ "amount_usd": 10.0 }
```

**Top-up Response:**
```json
{
  "client_secret": "pi_xxx_secret_xxx",
  "credits_to_grant": 333.33,
  "amount_usd": 10.0
}
```

Use the `client_secret` with Stripe.js `confirmPayment()`.

**Usage Event:**
```json
{ "id": "uuid", "model_alias": "deepseek", "credits_burned": "0.0523", "created_at": "..." }
```

**Transaction:**
```json
{
  "id": "uuid",
  "kind": "debit",
  "amount": "-0.0523",
  "initiated_by": null,
  "note": "Turn turn-uuid",
  "reference_id": "turn-uuid",
  "created_at": "..."
}
```

---

### Admin (requires admin role)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/admin/pricing` | Admin | List all model pricing |
| PATCH | `/admin/pricing/{model_alias}` | Admin | Update model multiplier |
| GET | `/admin/usage/summary` | Admin | System-wide usage summary |
| GET | `/admin/analytics/usage` | Admin | Per-user usage analytics |
| GET | `/admin/analytics/active-users` | Admin | Active/new user counts |
| GET | `/admin/settings` | Admin | System settings |
| PATCH | `/admin/settings/enforcement` | Admin | Toggle credit enforcement |
| DELETE | `/admin/settings/enforcement` | Admin | Clear enforcement override |
| GET | `/admin/wallets/{user_id}` | Admin | View user wallet |
| POST | `/admin/wallets/{user_id}/grant` | Admin | Grant credits to user |
| POST | `/admin/users/{user_id}/wallet/grant` | Admin | Grant credits (alt endpoint) |

**Admin returns 403** if user_id is not in the `ADMIN_USER_IDS` list.

**Usage Summary Query Params:**
- `user_id` (optional) — filter to specific user
- `model_alias` (optional) — filter to specific model
- `from_date`, `to_date` (optional) — date range
- `bucket` (optional) — `day`, `week`, or `month` for time series

**Usage Summary Response:**
```json
{
  "total_credits_burned": "1234.5678",
  "total_llm_calls": 5678,
  "total_output_tokens": 234567,
  "from_date": "2026-02-01",
  "to_date": "2026-02-28",
  "breakdown": [
    { "model_alias": "deepseek", "call_count": 3000, "credits_burned": "500.00" },
    { "model_alias": "premium", "call_count": 200, "credits_burned": "734.56" }
  ],
  "daily": [
    { "date": "2026-02-01", "credits_burned": "45.23", "call_count": 150 }
  ]
}
```

**Active Users Response:**
```json
{ "window": "week", "as_of": "2026-02-28", "active_users": 42, "new_users": 7 }
```

**Admin Grant Request:**
```json
{ "amount": 100.0, "note": "Welcome bonus" }
```

---

### Webhooks (no auth, signature-verified)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/webhooks/stripe` | Stripe signature | Handle payment completion |

This is called by Stripe when a payment intent succeeds. It grants credits to the user's wallet. The frontend does NOT call this directly.

---

## 9. SSE Streaming Protocol

**Endpoint:** `POST /api/v1/sessions/{sessionId}/turns/stream`

**Request headers:**
```
Authorization: Bearer {token}
Content-Type: application/json
Accept: text/event-stream
```

**Response:** `text/event-stream` with `Cache-Control: no-cache`

### Event Format

Each event is a JSON object on a `data:` line:
```
data: {"type": "agent_start", "agent_name": "Analyst", "agent_key": "analyst"}

data: {"type": "chunk", "delta": "Based on "}

data: {"type": "chunk", "delta": "my analysis, "}

data: {"type": "done", "turn_id": "uuid", ...}
```

### Event Types

| Event | Fields | When | How to render |
|-------|--------|------|---------------|
| `manager_think` | `phase`, `round`, `target_agents[]` (routing) or `decision` (evaluation) | Orchestrator mode: manager makes routing or evaluation decision | System card between agent responses |
| `agent_start` | `agent_name`, `agent_key` | Agent begins generating | Create new message bubble with agent label |
| `chunk` | `delta` | Incremental text from agent | Append to current agent's message content |
| `agent_end` | `agent_name` | Agent finished generating | Finalize message |
| `tool_start` | `tool`, `args` | Agent calls a tool | Show tool invocation indicator |
| `tool_end` | `tool`, `result` | Tool returns result | Show tool result (optional) |
| `round_start` | `round` | New orchestrator round begins | Optional round divider |
| `round_end` | `round` | Orchestrator round ends | Optional round divider |
| `error` | `message` | Error occurred | Show error as system message |
| `done` | `turn_id`, metadata | Turn complete | Finalize all messages, update session state |

### Manager Think Rendering

**Routing phase (orchestrator selects specialists):**
```
+------------------------------------------------------+
| ⚙️ Manager Routing (Round 1)                         |
| ↳ Selected Agents: @analyst, @strategist             |
+------------------------------------------------------+
```

**Evaluation phase (orchestrator decides next step):**
```
+------------------------------------------------------+
| ⚙️ Manager Evaluation                                |
| ↳ Decision: End specialist rounds. Synthesizing.     |
+------------------------------------------------------+
```

### Reading the SSE Stream

Use `fetch()` + `ReadableStream`:

```javascript
const response = await fetch(url, { method: "POST", headers, body });
const reader = response.body.getReader();
const decoder = new TextDecoder();
let buffer = "";

while (true) {
  const { done, value } = await reader.read();
  if (done) break;

  buffer += decoder.decode(value, { stream: true });
  // Split on \r?\n to handle both LF and CRLF line endings
  const lines = buffer.split(/\r?\n/);
  buffer = lines.pop(); // keep incomplete line in buffer

  for (const line of lines) {
    if (line.startsWith("data: ")) {
      const data = JSON.parse(line.slice(6));
      // handle event by data.type
    }
  }
}
```

**Important:** Split on `/\r?\n/` (not just `\n`) to handle both LF and CRLF line endings per the SSE specification.

---

## 10. Room Modes & Interaction Design

### Manual / Tag Mode ("Solo Chat")

- User MUST tag an agent with `@agentkey` in their message
- If no valid tag: API returns `422 { code: "no_valid_tagged_agents" }`
- If 1 tag: mode set to `tag`, one agent responds
- If 2+ tags: mode auto-escalates to `roundtable` behavior

**UI consideration:** Show available agent keys as autocomplete suggestions when user types `@`. Display a hint in the input: "Tag an agent with @key to start"

### Roundtable Mode ("Team Discussion")

- All assigned agents respond sequentially in position order
- Each agent sees what previous agents said (appended as context)
- `@mentioned` agents get priority (respond first)
- Anti-roleplay enforcement: agents cannot speak for other agents. Stop sequences and post-processing sanitization prevent multi-speaker contamination

**UI consideration:** Each agent's response should be a distinct message block with the agent name as a label. Show them appearing one after another during streaming.

### Orchestrator Mode ("Auto Best Answer")

The most complex mode. Flow:

1. **Manager routes:** Reads user question, selects 1-3 specialists, writes specific instructions for each
2. **Specialists respond:** Selected agents answer with their expertise
3. **Manager evaluates:** Decides if another round is needed (max 3 rounds, max 12 total specialist invocations)
4. **Manager synthesizes:** Produces a final consolidated answer combining all specialist outputs

**UI consideration:**
- Show manager routing decisions as system cards between agent responses
- Show each specialist response in its own labeled block
- Show manager evaluation decisions
- Show the final synthesis as a distinct "Manager Synthesis" block, separated by a horizontal divider
- If multiple rounds occur, consider showing round numbers or grouping

**Orchestrator constraints:**
- Requires at least 1 agent assigned to the room
- Room should have a `goal` set (API validates this)
- Max depth: 3 rounds
- Max specialist invocations: 12 per turn

---

## 11. Billing, Credits & Wallet

### How Credits Work

1. **Every LLM call costs credits.** Cost depends on token usage and model pricing multiplier.
2. **Formula:**
   - Output-Equivalent tokens: `OE = (input_fresh * 0.35) + (input_cached * 0.10) + output_tokens`
   - Credits burned: `OE * multiplier / 10,000`
3. **Model multipliers:** Set by admin. Example: `deepseek=0.5` (half price), `premium=2.0` (double price)
4. **1 USD = ~33.33 credits** at default rate ($0.03 per credit)

### Enforcement

- When `credit_enforcement_enabled = true`: users with 0 balance get HTTP 402 on turn submission
- Admin can toggle enforcement via `PATCH /admin/settings/enforcement`
- Turn responses include `balance_after` (string decimal) and `low_balance` (boolean)

### Stripe Top-Up Flow

1. User chooses amount ($1–$500)
2. Frontend calls `POST /users/me/wallet/top-up` with `{ amount_usd }`
3. Backend creates Stripe PaymentIntent, returns `client_secret`
4. Frontend uses Stripe.js Elements to collect card and confirm payment
5. Stripe sends webhook to `POST /webhooks/stripe`
6. Backend verifies signature, grants credits to wallet
7. Frontend polls `GET /users/me/wallet` to see updated balance

### Transaction Kinds

| Kind | Direction | Description |
|------|-----------|-------------|
| `grant` | Positive | Credits added (Stripe top-up, admin grant) |
| `debit` | Negative | Credits spent on LLM calls |
| `refund` | Positive | Credits returned (future feature) |

---

## 12. Admin Dashboard

Full admin feature set. All endpoints return 403 for non-admin users.

### Pages to Build

#### 12.1 Pricing Configuration
- Table of all models with their multipliers
- Editable multiplier field (range: 0.01 to 100.0)
- Shows pricing version

#### 12.2 Usage Dashboard
- **Summary cards:** Total credits burned, total LLM calls, total output tokens
- **Filters:** Date range picker, user ID filter, model filter, bucket selector (day/week/month)
- **Charts:** Daily usage bar chart, model breakdown pie chart
- **Per-user table:** Sortable by credits_burned, filterable by date range

#### 12.3 Active Users
- Metric cards showing active users and new users
- Period selector: Day / Week / Month
- Historical trend (call endpoint with different `as_of` dates)

#### 12.4 System Settings
- Credit enforcement toggle (on/off)
- Show current source: "config" (from env) vs "override" (admin-set)
- Low balance threshold display
- Active pricing version

#### 12.5 User Wallet Management
- Search by user_id
- Display: current balance, recent transactions (last 10)
- Grant credits form: amount + optional note
- Transaction history table

---

## 13. File Uploads

### Upload Flow

1. User clicks upload button (📎)
2. File picker opens (restricted to allowed types)
3. File uploaded as `multipart/form-data` to `POST /rooms/{roomId}/files` or `POST /sessions/{sessionId}/files`
4. Backend stores in Supabase Storage, parses content (text extraction for PDFs, DOCX, etc.)
5. Parse status tracked: `pending` → `completed` or `failed`

### Display

Show uploaded files in the room/session workspace:
- File name
- Parse status indicator (green dot = completed, orange = pending, red = failed)
- File size
- Upload timestamp

### How Agents Use Files

When files are uploaded to a room, agents with `file_read` permission see:
```
The user has uploaded the following files to this room:
- report.pdf (ID: uuid-xxx)
- data.csv (ID: uuid-yyy)

To read a file, use the 'file_read' tool with its ID.
```

This is automatically injected into the agent's context. The agent can then call the `file_read` tool to read the file's parsed content.

---

## 14. Current Frontend State

The Next.js frontend at `apps/web/` is partially built (~30-40% complete):

### What Exists
- Auth flow (login, callback, middleware guards)
- Agent CRUD page (`/agents`)
- Room list page (`/rooms`) with create/delete
- Room workspace page (`/rooms/[roomId]`) with:
  - Mode switching
  - Agent assignment
  - Session management
  - Chat with SSE streaming
  - File upload
- API client modules for all entity types
- Design system (dark theme, Tailwind config, CSS variables)
- React Query setup, Zustand store

### What's Missing
- Billing page (empty stub)
- Admin dashboard (no pages exist)
- User profile / settings page
- Agent update/edit (only create and delete)
- Room goal editing
- Pagination UI for long lists
- Search across entities
- Real-time updates (currently polling via React Query)
- Session history export
- Accessibility audit
- Error tracking / monitoring integration

### Dependencies Installed
- Next.js 14, React 18, TypeScript
- Tailwind CSS 3.4, PostCSS, Autoprefixer
- @supabase/ssr, @supabase/supabase-js
- @tanstack/react-query v5
- Zustand v5
- clsx, tailwind-merge, class-variance-authority
- lucide-react (icons)

---

## 15. Design System & Tokens

### CSS Custom Properties (defined in `globals.css`)

```css
:root {
  --bg-base: #09090b;        /* Page background */
  --bg-surface: #18181b;      /* Card/panel backgrounds */
  --bg-elevated: #27272a;     /* Hover states, active items */
  --text-primary: #fafafa;    /* Primary text */
  --text-muted: #71717a;      /* Secondary/placeholder text */
  --accent: #7c3aed;          /* Primary accent (purple) */
  --accent-hover: #6d28d9;    /* Accent hover state */
  --border: #3f3f46;          /* Borders and dividers */
}
```

### Tailwind Mapping

Colors are mapped in `tailwind.config.js`:
```js
colors: {
  background: "var(--bg-base)",
  surface: "var(--bg-surface)",
  elevated: "var(--bg-elevated)",
  border: "var(--border)",
  foreground: "var(--text-primary)",
  muted: "var(--text-muted)",
  accent: { DEFAULT: "var(--accent)", hover: "var(--accent-hover)" },
}
```

### Component Patterns

- **Buttons:** Use `class-variance-authority` for variants (default: accent bg, ghost: transparent)
- **Cards:** `bg-surface` background, `border border-border` border, `rounded-xl` corners
- **Modals:** Overlay with backdrop blur, centered card, title + close button
- **Inputs:** Dark background matching surface, border on focus, placeholder in muted
- **Status badges:** Colored pills — green (success), orange (pending), red (error), purple (accent)
- **Icons:** `lucide-react` icon library

### Typography

- Font family: Inter, Segoe UI, Arial, sans-serif
- Agent name labels: uppercase, 10px, bold, letter-spacing 0.6px, green/accent color
- System messages: italic, dimmed text color

---

## 16. test_ui.html Reference Implementation

**Location:** `/test_ui.html` (project root)
**Served at:** `GET /test-console`
**Size:** ~1,268 lines of self-contained HTML/CSS/JS

**This file is your most important reference.** It implements every feature of the platform in vanilla JavaScript — no frameworks, no build tools. While the production frontend uses React/Next.js, `test_ui.html` demonstrates the correct API call sequences, event handling, and UI patterns.

### What to Study in test_ui.html

#### API Call Patterns (lines 688-750)
- The generic `api()` function wraps fetch with auth headers
- Health check → load agents → load rooms (initialization sequence)
- Error handling with response.ok checks and JSON error parsing

#### SSE Streaming (lines 1094-1187)
- Full implementation of `ReadableStream` + `TextDecoder` for SSE parsing
- Buffer management for incomplete lines
- Event type dispatching: `manager_think`, `agent_start`, `chunk`, `error`
- How to create message elements incrementally and auto-scroll

#### Orchestrator Event Rendering (lines 1143-1158)
- Manager routing cards: round number, selected agents with @notation
- Manager evaluation cards: continue vs synthesize decisions
- Styling: dark background, left border, italic gray text

#### File Upload (lines 1226-1263)
- FormData construction (NOT JSON)
- Room-level vs session-level upload endpoints
- Status indicator rendering (colored dots for parse status)

#### Mode Switching (lines 879-901)
- PATCH request to change mode
- UI revert on error
- CSS class mapping for mode badges

#### Agent Assignment (lines 1052-1072)
- Modal with agent dropdown and position input
- POST to room agents endpoint
- Refresh agent list after assignment

#### Session Management (lines 938-998)
- Create, list, select, delete sessions
- Message loading on session select
- Session ID display (truncated to 8 chars)

#### Multi-Agent Response Rendering
- Each agent gets its own labeled message block
- Agent label: uppercase, colored, small font above the response
- Manager synthesis separated by horizontal rule (`---`)

**Key patterns to replicate in React:**
1. The initialization sequence (health → agents → rooms)
2. The SSE event loop with buffer management
3. The manager_think card rendering between agent responses
4. The file upload using FormData (not JSON)
5. The mode badge color mapping

---

## 17. User Stories & Expected Behaviors

For comprehensive end-to-end scenarios covering all features, see `docs/state_machine_agent_room_user_stories.md`. It contains 30 elaborated user stories with:

- Realistic situations and example user messages
- Step-by-step flows
- Expected outcomes (HTTP status codes, persisted state, UI behavior)
- Test execution results (28/30 pass, 2 test-harness artifacts)

Key scenarios to understand:

| # | Story | Key Behavior |
|---|-------|-------------|
| 1 | Council bootstrap | Full orchestrator flow from room creation to synthesis |
| 7 | Orchestrator guardrail | Room creation requires goal for orchestrator mode |
| 8 | Mode transitions | Same room switches between all three modes |
| 17 | Manual mode tagging | Untagged message rejected with 422 |
| 19 | Multi-tag escalation | 2+ @mentions auto-upgrade to roundtable |
| 20 | Roundtable priority | @mentioned agent speaks first |
| 22 | Orchestrator subset | Manager routes to relevant specialists only |
| 24 | Multi-round orchestrator | Manager decides continue/stop between rounds |
| 27 | Streaming happy path | SSE event sequence for non-tool agents |
| 28 | Streaming with tools | Tool events visible during streaming |
| 29 | Tool memory | Agent remembers previous tool calls |
| 30 | Stress: files + billing + rate limiting | Full integration test |

### Rate Limiting

- Per-user limits: 10 turns/minute, 60 turns/hour
- When exceeded: HTTP 429 with `Retry-After` header
- UI should show a "slow down" message and respect the retry-after period

### Error States to Handle

| HTTP Code | Meaning | UI Action |
|-----------|---------|-----------|
| 401 | Token expired | Redirect to login |
| 402 | Insufficient credits | Show top-up prompt |
| 403 | Not admin | Show access denied |
| 404 | Resource not found | Show not found message |
| 409 | Conflict (duplicate key) | Show conflict message |
| 422 | Validation error (e.g., no @tag) | Show specific error detail |
| 429 | Rate limited | Show retry countdown |
| 500+ | Server error | Show generic error + retry |

---

## Appendix: Quick Start Checklist

For a new UI/UX developer joining the project:

1. Read this document end to end
2. Open `http://localhost:8030/test-console` and use every feature (create agents, create room, assign agents, switch modes, send messages in all three modes, upload a file, check orchestrator routing)
3. Read `test_ui.html` source code — especially the SSE streaming section and orchestrator event rendering
4. Read `docs/state_machine_agent_room_user_stories.md` for expected behaviors
5. Explore the existing Next.js frontend at `apps/web/src/`
6. Check the design tokens in `apps/web/src/app/globals.css` and `tailwind.config.js`
7. Set up local env: `NEXT_PUBLIC_API_BASE_URL=http://localhost:8030`, Supabase keys, `NEXT_PUBLIC_ENABLE_DEV_PASSWORD_LOGIN=true`
