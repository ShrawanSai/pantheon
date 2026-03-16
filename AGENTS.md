# AGENTS.md — Pantheon

## Version Control and Branching Strategy

- **Branching Model**: GitHub Flow.
    - **`main`**: The primary branch. Always deployable and stable.
    - **`custom_agent_implementation`**: The current active development branch containing the full product implementation. This branch will eventually be merged into `main`.
    - **Feature/Fix Branches**: Create new branches for all changes (e.g., `feat/agent-ui`, `fix/db-migration`). Merge into `main` via Pull Request after CI passes.
- **Commit Messages**: Follow the [Conventional Commits](https://www.conventionalcommits.org/) specification (e.g., `feat: ...`, `fix: ...`).
- **Pull Requests**: Required for all changes to `main`. Ensure CI (Backend + Frontend jobs) passes before merging.

## Project Overview

Pantheon is a multi-agent AI chat platform with a Python/FastAPI backend, arq background worker, and Next.js/React/TypeScript frontend. Deployed on Railway (API + worker) with Supabase for auth and Postgres for data.

## Repository Structure

```
apps/api/app/          # FastAPI backend (main.py is the entry point)
  api/v1/routes/       # Route handlers (one file per resource)
  core/                # Settings (frozen dataclass + lru_cache)
  db/                  # SQLAlchemy 2.0 models + async session factory
  schemas/             # Pydantic v2 request/response schemas
  services/            # Business logic (billing, orchestration, LLM, tools, usage)
  dependencies/        # FastAPI Depends() factories (auth, rooms, arq)
  workers/             # arq worker + background jobs
apps/web/              # Next.js 14 App Router frontend
  src/app/             # Pages & layouts (route groups: (authed)/, auth/)
  src/components/      # React components (ui/, common/, layout/, rooms/, providers/)
  src/lib/             # API client, Zustand store, Supabase helpers, utilities
tests/                 # Backend unit/integration tests (unittest, root-level)
infra/alembic/         # Database migrations
scripts/               # Utility/smoke-test scripts
```

## Build, Lint, and Test Commands

### Backend (Python 3.13)

**IMPORTANT**: Always use the project's `.venv` virtual environment, not system Python. The venv has all required dependencies installed.

```bash
# Install dependencies (if needed - usually already set up)
pip install -r requirements.txt
pip install ruff

# Run dev server (hot-reload on port 8010)
.venv/Scripts/python.exe run_dev.py

# Lint (critical rules only, matches CI)
.venv/Scripts/python.exe -m ruff check apps/api/app tests scripts/w1_arq_smoke_enqueue.py --select E9,F63,F7,F82

# Compile check (import sanity)
.venv/Scripts/python.exe -m compileall apps/api/app scripts

# Run ALL tests
.venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py" -v

# Run a SINGLE test file
.venv/Scripts/python.exe -m unittest tests.test_wallet_service -v

# Run a SINGLE test method
.venv/Scripts/python.exe -m unittest tests.test_wallet_service.WalletServiceTests.test_stage_debit_reduces_balance -v
```

### Frontend (Node 22)

**IMPORTANT**: Next.js 14 requires Node.js >= 18.17.0. Use `fnm` to switch to Node 22:

```bash
# Switch to Node 22 (run once per shell session)
eval "$(fnm env)" && fnm use 22

cd apps/web

npm ci              # Install dependencies (use ci, not install)
npm run dev         # Dev server
npm run build       # Production build + typecheck (this IS the CI check)
npm run lint        # Next.js ESLint
```

### CI Pipeline (GitHub Actions)

The `ci.yml` workflow runs on push to `main` and all PRs:
- **Backend job**: `ruff check` (critical rules) -> `unittest discover` -> `compileall` -> worker import sanity
- **Frontend job**: `npm ci` -> `npm run build`

## Python Code Style

### Imports

Every Python file starts with `from __future__ import annotations`, then:
1. Standard library (alphabetical)
2. Third-party (`fastapi`, `sqlalchemy`, `pydantic`, `arq`, etc.)
3. Local imports using absolute paths (`apps.api.app.*`)

### Naming

| Element | Convention | Example |
|---------|-----------|---------|
| Functions/variables | `snake_case` | `create_room`, `user_id` |
| Classes | `PascalCase` | `WalletService`, `RoomCreateRequest` |
| Module logger | `_LOGGER` | `_LOGGER = logging.getLogger(__name__)` |
| Private helpers | `_prefix` | `_room_to_read`, `_seed_wallet` |
| Constants/regex | `_SCREAMING_SNAKE` | `_TAG_PATTERN` |

### Type Annotations

- Annotate all function parameters and return types.
- Use modern union syntax: `str | None` (not `Optional[str]`).
- Use lowercase generics: `list[str]`, `dict[str, str]` (not `List`, `Dict`).
- SQLAlchemy columns use `Mapped[T]` with `mapped_column(...)`.
- Constrained strings use `Literal`: `RoomMode = Literal["manual", "tag", "roundtable", "orchestrator"]`.

### Pydantic Schemas

- Always set `model_config = ConfigDict(extra="forbid")`.
- Naming: `XxxCreateRequest` / `XxxUpdateRequest` for input, `XxxRead` / `XxxListRead` for output.
- Use `Field(min_length=..., max_length=..., gt=..., le=...)` for constraints.
- Validators use `@field_validator("field")` + `@classmethod`.
- Money/credits: store as `Decimal`, serialize as `str` in API responses (never `float`).

### SQLAlchemy Models

- All models in `db/models.py`, inheriting from `Base(DeclarativeBase)`.
- `__tablename__` is explicit, plural snake_case: `"rooms"`, `"credit_wallets"`.
- Primary keys are `String(64)` with `str(uuid4())` generated in Python.
- Timestamps: `created_at` / `updated_at` with `server_default=text("CURRENT_TIMESTAMP")`.
- Soft deletes via `deleted_at: Mapped[datetime | None]`, filtered with `.is_(None)`.
- Constraint naming: `uq_` for unique, `ck_` for check.

### Error Handling

- Routes raise `HTTPException` with specific status codes (401, 402, 403, 404, 409, 413, 422, 429).
- 422 errors use structured detail: `{"code": "...", "message": "..."}`.
- 429 errors include `Retry-After` header.
- `IntegrityError` from SQLAlchemy is caught, rolled back, and raised as 409.
- Services raise `ValueError`; routes catch and convert to `HTTPException`.

### Logging

- Use `_LOGGER = logging.getLogger(__name__)` (standard library only).
- Format: `"function_name:phase key=%s"` with `%s` placeholders (not f-strings).
- Phases: `:start`, `:done`, with `:skip` or `:fallback` for edge cases.

### Service Layer Pattern

- Services use a two-phase commit: `stage_*()` methods modify the session without committing.
- The route handler calls `await db.commit()` after all service operations.
- Convenience `record_*()` methods commit in standalone contexts.
- Services are module-level singletons exposed via `get_x()` factory functions.

### Dependency Injection

- `get_current_user()` returns `dict[str, str]` with `user_id` and `email`.
- `get_db()` yields an `AsyncSession` via async generator.
- Service singletons: `_wallet_service = WalletService()` + `get_wallet_service()`.
- Dev overrides: `"dev-override"` and `"admin-override"` bearer tokens in non-prod.

### Tests (unittest)

- Framework: `unittest.TestCase` (not pytest). Async bridged via `asyncio.run()`.
- In-memory SQLite with `aiosqlite` + `StaticPool` for all DB tests.
- FastAPI dependency overrides in `setUpClass` / `tearDownClass`.
- Fake services as `@dataclass` classes (e.g., `FakeStorageService`, `FakeArqRedis`).
- Seed helpers: `_seed_user_and_room()`, `_seed_agent()`, `_seed_wallet()`.
- Test naming: `test_<action>_<expected_behavior>`.
- Set dummy env vars at module level for CI: `os.environ.setdefault(...)`.

## TypeScript/React Code Style (apps/web/)

### Components

- Use **named function declarations** for all components (no arrow-function components).
- Page components: `export default function XxxPage() { ... }`.
- Shared components: `export function XxxComponent({ ... }: Props) { ... }`.
- Only exception: `React.forwardRef` uses arrow (shadcn/ui `Button`).

### Files and Naming

- Files: **kebab-case** (`create-room-modal.tsx`, `ui-store.ts`).
- Components/types: **PascalCase** (`CreateRoomModal`, `RoomRead`).
- Variables/functions: **camelCase** (`queryClient`, `handleSendTurn`).
- Constants: **UPPER_SNAKE_CASE** (`MODE_LABELS`, `CREDITS_PER_USD`).
- API response types use `Read` suffix; request types use `Request`/`Payload` suffix.

### Imports

1. React/Next.js framework imports
2. Third-party libraries (`@tanstack/react-query`, `lucide-react`, etc.)
3. Internal `@/*` path alias imports (maps to `src/*`)

Use `import type { X }` for type-only imports. No relative `../` imports within `src/`.

### Types

- Use `type` aliases exclusively (not `interface`, except shadcn/ui `ButtonProps`).
- Discriminated unions for stream events: `type StreamEvent = StreamChunkEvent | StreamDoneEvent | ...`.
- TypeScript strict mode is enabled. Avoid `any`; use `unknown` or `Record<string, unknown>`.

### State Management

- **Server data**: TanStack React Query v5 (`useQuery`, `useMutation`, `queryClient.invalidateQueries`).
- **Client UI state**: Zustand (single `useUIStore` for sidebar toggle).
- **Local state**: `useState` / `useRef`.
- Query keys: `["rooms"]`, `["room", roomId]`, `["sessionMessages", sessionId]`.

### API Calls

- Central `apiFetch<T>(path, init)` in `lib/api/client.ts` handles auth headers, timeouts, 401 redirects.
- Domain modules (`rooms.ts`, `agents.ts`, etc.) are thin wrappers returning `Promise<T>`.
- SSE streaming uses `ReadableStream.getReader()` with custom SSE parser.
- Custom `ApiError` class with `status` and `detail` properties.

### Styling

- Tailwind CSS with semantic CSS custom properties (`bg-surface`, `text-foreground`, `border-border`).
- Dark mode via `next-themes` (class strategy, default dark).
- Conditional classes via array `.join(" ")` or template literals.
- `cn()` utility (clsx + tailwind-merge) for variant composition.
- Fonts: Playfair Display (serif headings) + Outfit (sans body).

## Deployment & Infrastructure

### Tech Stack Overview

**Frontend**: Next.js 14 → Vercel
**Backend**: Python/FastAPI + arq Worker → Railway
**Database**: PostgreSQL → Supabase
**Queue**: Redis → Railway
**Auth**: Supabase Auth
**AI**: OpenRouter API

See comprehensive details in `TECH-STACK.md` at repository root.

### Railway Deployment

**Environments**:
- `production`: Live user-facing environment (deploys from `main`)
- `staging`: Testing environment

**Services** (per environment):
- `api`: FastAPI application
- `worker`: arq background job processor
- `Redis`: Redis 8.2.1 for queuing

**Service IDs**:
- Project: `95e392ab-db2e-49f7-8c34-5aeac5a72668`
- API: `e5dd96bc-8a2d-47fd-8603-c8218f4d1773`
- Worker: `ffa57017-0fcd-44e1-91a3-4a3d43ba03d5`
- Redis: `82826ce0-5d8e-40f6-a56d-3e56ab90b644`

**URLs**:
- Production API: `api-production-97ea.up.railway.app`
- Production Worker: `worker-production-d952.up.railway.app`
- Staging API: `api-staging-3c02.up.railway.app`

**Deploy Triggers**: Automatic on push to `main` branch via GitHub Actions

### Supabase Configuration

**Project**: `wpxmmnttpehmwhokpqms` (us-east-1)
**Services**: PostgreSQL 15 + Auth

**Connection Strings**:
- Direct: `postgresql://postgres:sai.kjjsg79961@db.wpxmmnttpehmwhokpqms.supabase.co:5432/postgres`
- Pooler: `postgresql://postgres.wpxmmnttpehmwhokpqms:sai.kjjsg79961@aws-1-ca-central-1.pooler.supabase.com:6543/postgres`

**Keys** (in `.env`):
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`

### Environment Variables

**Critical Env Vars** (check `.env` and `.env.local`):
- `DATABASE_URL` / `DATABASE_POOL_URL`
- `REDIS_URL` (Railway Redis)
- `OPENROUTER_API_KEY`
- `SUPABASE_*` keys
- `RAILWAY_*` (auto-injected by Railway)

**Environment-Specific**:
- Local: `.env` + `apps/web/.env.local`
- Production: Railway dashboard + `.env`
- Staging: Railway dashboard (separate env)

### Current Status (as of last check)

**Production**:
- 🔴 API: CRASHED - needs investigation
- 🟢 Worker: Running
- 🟢 Redis: Running

**Staging**:
- 🟢 API: Running
- 🟢 Worker: Running
- 🟢 Redis: Running

### Debug Logging

- `debugLog(scope, message, payload?)` / `debugWarn` / `debugError` from `lib/debug.ts`.
- Enabled via `NEXT_PUBLIC_DEBUG_LOGS=true` or `localStorage.pantheon_debug=1`.
- Scope naming: `"rooms-page"`, `"turn-send"`, `"session-drawer"`.

- `debugLog(scope, message, payload?)` / `debugWarn` / `debugError` from `lib/debug.ts`.
- Enabled via `NEXT_PUBLIC_DEBUG_LOGS=true` or `localStorage.pantheon_debug=1`.
- Scope naming: `"rooms-page"`, `"turn-send"`, `"session-drawer"`.
