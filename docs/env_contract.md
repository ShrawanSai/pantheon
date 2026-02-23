# Pantheon MVP Environment Contract

Date: 2026-02-20  
Scope: Week 1 environment variable contract for frontend/backend/worker

## 1. Rules
1. Do not commit real secrets.
2. `.env.example` is the canonical template for local development.
3. Production/staging secrets must be stored in hosting secret managers (Vercel/Railway/Supabase), not in files.
4. `DATABASE_URL` and `DATABASE_POOL_URL` are both required:
- `DATABASE_URL` for migrations/admin operations.
- `DATABASE_POOL_URL` for runtime API/worker connections.

## 2. Variable Matrix

| Variable | Required | Service Owner | Used By | Purpose |
|---|---|---|---|---|
| `OPENROUTER_API_KEY` | Yes | Backend | API, Worker | Authenticate LLM requests to OpenRouter |
| `OPENROUTER_BASE_URL` | Yes | Backend | API, Worker | OpenRouter base endpoint |
| `SUPABASE_URL` | Yes | Platform | API, Frontend | Supabase project URL |
| `SUPABASE_ANON_KEY` | Yes | Platform | Frontend, API (verification flows) | Public anon key for client auth flows |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | Platform | API, Worker | Server-side privileged Supabase operations |
| `DATABASE_URL` | Yes | Platform | API (migrations), Worker (maintenance jobs) | Direct Postgres URL |
| `DATABASE_POOL_URL` | Yes | Platform | API, Worker | Pooled Postgres URL (runtime) |
| `REDIS_URL` | Yes | Platform | API, Worker | Queue backend for arq |
| `API_HOST` | Yes (local) | Backend | API | Bind host for FastAPI |
| `API_PORT` | Yes (local) | Backend | API | Bind port for FastAPI |
| `API_BASE_URL` | Yes | Backend | API, Frontend | Canonical API base URL for local/dev |
| `API_CORS_ALLOWED_ORIGINS` | Yes | Backend | API | Allowed origins for frontend calls |
| `NEXT_PUBLIC_API_BASE_URL` | Yes | Frontend | Frontend | Browser-callable backend base URL |
| `NEXT_PUBLIC_SUPABASE_URL` | Yes | Frontend | Frontend | Supabase URL for auth client |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Yes | Frontend | Frontend | Supabase anon key for auth client |
| `STRIPE_SECRET_KEY` | Yes (payments enabled) | Backend | API | Stripe secret key for PaymentIntent creation |
| `STRIPE_WEBHOOK_SECRET` | Yes (payments enabled) | Backend | API | Stripe webhook signature verification secret |
| `RATE_LIMIT_TURNS_PER_MINUTE` | No (default `10`) | Backend | API | Per-user burst protection on turn submit endpoints |
| `RATE_LIMIT_TURNS_PER_HOUR` | No (default `60`) | Backend | API | Per-user hourly turn cap on turn submit endpoints |

## 3. Environment Mapping

## 3.1 Local Dev
- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`
- Redis: local or managed development instance
- Database: Supabase development project

## 3.2 Staging
- Frontend: Vercel preview/staging domain
- Backend: Railway staging service URL
- DB/Storage/Auth: Supabase staging project
- Redis: Railway staging Redis

## 3.3 Production
- Frontend: Vercel production domain
- Backend: Railway production service URL
- DB/Storage/Auth: Supabase production project
- Redis: Railway production Redis

## 4. Week 1 Provisioning Placeholders (Non-Secret)
Populate these during W1-05:
1. Supabase project ref/URL
2. Railway API service URL
3. Railway worker service URL
4. Railway Redis instance URL
5. Vercel project URL

## 5. Payment Webhook Contract
- Webhook endpoint path: `/webhooks/stripe`
- Auth: no JWT required (Stripe signature verification instead)
- Local testing shortcut:
  - If `STRIPE_WEBHOOK_SECRET` is unset, signature verification is skipped.
  - This shortcut is for local/non-production testing only.
