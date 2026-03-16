# Pantheon Tech Stack & Deployment Architecture

## Overview
Pantheon is a multi-agent AI chat platform deployed across **three cloud providers** with a clear separation between frontend, backend, and infrastructure services.

---

## 🏗️ Core Architecture

### **Monorepo Structure**
```
/apps/api          → Python/FastAPI backend (Railway)
/apps/web          → Next.js/React frontend (Vercel)
infra/alembic      → Database migrations
/tests             → Backend tests
```

### **Traffic Flow**
```
User Browser → Vercel Frontend → Railway API → Supabase (Auth + DB) → OpenRouter AI
                                     ↓
                                Railway Worker (arq queue)
```

---

## 🖥️ Frontend (Vercel)

**Service**: Next.js 14 App Router
**Deploy Platform**: Vercel
**URL**: (configured in Vercel dashboard)

**Key Configurations**:
- **Framework**: Next.js 14.2.5 with TypeScript
- **Build Command**: `npm run build`
- **Dev Server**: `npm run dev` on port 3000
- **API Proxy**: Proxies requests to Railway API

**Environment Variables** (`.env.local`):
```
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8010 (local) / Railway URL (production)
NEXT_PUBLIC_SUPABASE_URL=https://wpxmmnttpehmwhokpqms.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJhbGci...
NEXT_PUBLIC_DEBUG_LOGS=true
```

**Purpose**:
- User-facing web interface
- Authentication via Supabase Auth
- Real-time chat with AI agents
- Session management and billing UI

---

## ⚙️ Backend (Railway)

**Service**: Python/FastAPI + arq Worker
**Deploy Platform**: Railway.app
**Location**: `us-west2` region

### **Production Environment** (`main` branch)

#### **API Service** - ❌ **CRASHED**
**Service ID**: `e5dd96bc-8a2d-47fd-8603-c8218f4d1773`
**URL**: `https://api-production-97ea.up.railway.app`
**Status**: **CRASHED** (needs investigation)
**Last Deploy**: 2026-03-15 18:40:22 UTC
**Commit**: `0280487ba` ("frontendstuff")

**Configuration** (`railway.api.toml`):
```toml
[build]
builder = "RAILPACK"

[deploy]
startCommand = "python -m uvicorn apps.api.app.main:app --host 0.0.0.0 --port $PORT"
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 10
```

**Runtime**:
- Python 3.13.12
- FastAPI with async SQLAlchemy
- Uvicorn ASGI server
- Port: `$PORT` (Railway-assigned)

#### **Worker Service** - ✅ **RUNNING**
**Service ID**: `ffa57017-0fcd-44e1-91a3-4a3d43ba03d5`
**URL**: `worker-production-d952.up.railway.app`
**Status**: ✅ **SUCCESS**
**Last Deploy**: 2026-03-15 18:40:22 UTC
**Purpose**: Background job processing (arq queue)

**Configuration** (`railway.worker.toml`):
```toml
[build]
builder = "RAILPACK"

[deploy]
startCommand = "python -m arq apps.api.app.workers.arq_worker.WorkerSettings"
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 10
```

#### **Redis Service** - ✅ **RUNNING**
**Service ID**: `82826ce0-5d8e-40f6-a56d-3e56ab90b644`
**Image**: `redis:8.2.1`
**Status**: ✅ **SUCCESS**
**Volume**: 49.6MB used of 500MB
**Purpose**: arq queue backend, caching

**Connection Details**:
```
Host: shinkansen.proxy.rlwy.net
Port: 18680
Password: JbfkLYKNsYuDgoWgornGqTPeKXcbbWWV
URL: redis://default:JbfkLYKNsYuDgoWgornGqTPeKXcbbWWV@shinkansen.proxy.rlwy.net:18680
```

---

### **Staging Environment** (`main` branch)

#### **API Service** - ✅ **RUNNING**
**URL**: `https://api-staging-3c02.up.railway.app`
**Status**: ✅ **SUCCESS**
**Last Deploy**: 2026-02-23 23:29:33 UTC
**Commit**: `c7c74a398` ("backend wrap_up")

#### **Worker Service** - ✅ **RUNNING**
**URL**: `worker-staging-d144.up.railway.app`
**Status**: ✅ **SUCCESS**
**Last Deploy**: 2026-02-23 15:38:17 UTC

#### **Redis Service** - ✅ **RUNNING**
**Image**: `redis:8.2.1`
**Status**: ✅ **SUCCESS**

---

## 🗄️ Database & Auth (Supabase)

**Service**: PostgreSQL + Authentication
**Provider**: Supabase
**Project**: `wpxmmnttpehmwhokpqms`
**Region**: AWS us-east-1 (N. Virginia)

### **PostgreSQL Database**

**Direct Connection** (for migrations, admin):
```
postgresql://postgres:sai.kjjsg79961@db.wpxmmnttpehmwhokpqms.supabase.co:5432/postgres
```

**Pooler Connection** (for app connections):
```
postgresql://postgres.wpxmmnttpehmwhokpqms:sai.kjjsg79961@aws-1-ca-central-1.pooler.supabase.com:6543/postgres
```

**Configuration**:
- PostgreSQL 15
- Connection Pooling: Transaction mode
- Pool Size: 10 (default)
- SSL: Required for external connections

### **Authentication**

**Supabase Auth** manages:
- User registration/login
- JWT tokens
- Magic link authentication
- Password reset
- Admin users (`ADMIN_USER_IDS`)

**Admin Users**:
```
9393e58d-bf6b-4f81-829a-6195ebb8411d
```

**Environment Variables**:
```
SUPABASE_URL=https://wpxmmnttpehmwhokpqms.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

---

## 🧠 AI Services (OpenRouter)

**Provider**: OpenRouter.ai
**Models**: Multiple LLM providers (OpenAI, Anthropic, etc.)

**Configuration**:
```
OPENROUTER_API_KEY=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
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

**Pricing**: Pay-per-token via OpenRouter

---

## 🚀 Build & Deploy Process

### **Local Development**

**Backend**:
```bash
python run_dev.py          # Runs on http://127.0.0.1:8010
```

**Frontend**:
```bash
cd apps/web && npm run dev # Runs on http://localhost:3000
```

### **CI/CD Pipeline** (GitHub Actions)

**Trigger**: Push to `main` branch or Pull Request

**Backend Job**:
1. Install Python 3.13
2. `pip install -r requirements.txt`
3. `ruff check` (critical rules only)
4. `python -m unittest discover` (all tests)
5. `python -m compileall` (import sanity)
6. Worker import sanity check

**Frontend Job**:
1. `npm ci` (clean install)
2. `npm run build` (production build + typecheck)

### **Deployment** (Railway)

**Automatic**: On push to `main` branch
**Build System**: Railpack (auto-detects Python/FastAPI)
**Regions**: us-west2 (multi-region config ready)

**Railway API Service**:
- **Build**: Railpack detects Python 3.13, FastAPI
- **Start**: `python -m uvicorn apps.api.app.main:app --host 0.0.0.0 --port $PORT`
- **Port**: Dynamic (`$PORT` env var)
- **Health**: No healthcheck path configured

**Railway Worker Service**:
- **Build**: Railpack detects Python 3.13, arq
- **Start**: `python -m arq apps.api.app.workers.arq_worker.WorkerSettings`
- **Queue**: Redis (arq)

**Railway Redis Service**:
- **Image**: Official Redis 8.2.1
- **Volume**: Persistent storage `/data`
- **Auth**: Password-protected

---

## 🌐 Networking & Domains

### **Production**
- **API**: `api-production-97ea.up.railway.app` (CRASHED)
- **Worker**: `worker-production-d952.up.railway.app` (RUNNING)
- **Private Network**: `pantheon.railway.internal`

### **Staging**
- **API**: `api-staging-3c02.up.railway.app` (RUNNING)
- **Worker**: `worker-staging-d144.up.railway.app` (RUNNING)

### **CORS Configuration**
```
API_CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```
*Note: Frontend domain needs to be added for production*

---

## 🔑 Key Environment Variables

### **Shared Across Environments**
```
# AI
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

# Database
DATABASE_URL=postgresql://...
DATABASE_POOL_URL=postgresql://...

# Redis
REDIS_URL=redis://default:...@shinkansen.proxy.rlwy.net:18680

# Supabase Auth
SUPABASE_URL=https://wpxmmnttpehmwhokpqms.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGc...
```

### **Railway-Injected**
```
RAILWAY_ENVIRONMENT=production|staging
RAILWAY_PROJECT_ID=95e392ab-db2e-49f7-8c34-5aeac5a72668
RAILWAY_SERVICE_NAME=api|worker|Redis
RAILWAY_PUBLIC_DOMAIN=*.up.railway.app
RAILWAY_PRIVATE_DOMAIN=pantheon.railway.internal
```

---

## ⚠️ Current Issues & Recommendations

### **🔴 CRITICAL: Production API Crashed**

**Status**: API service is CRASHED after latest deployment
**Impact**: Production application is down
**Error**: Unknown (needs log investigation)

**Immediate Actions Needed**:
1. View crash logs: `railway logs --service api --environment production`
2. Check for missing environment variables
3. Restart service: `railway restart --service api`
4. If persists, redeploy previous working commit: `c7c74a398`

**Possible Causes**:
- Database connection issue
- Missing environment variable
- Application code error
- Port binding issue (not listening on $PORT)
- Python dependency mismatch

---

## 📊 Resource Usage

### **Redis Volume**
- **Size**: 49.6MB used of 500MB
- **Mount**: `/data`
- **Backup**: Automatic snapshots

### **Service Limits** (Trial Plan)
- **CPU**: Shared
- **Memory**: 1GB per service
- **Build Time**: 30 minutes max
- **Deploy**: Automatic restart on failure (max 10 retries)

---

## 🔒 Security

### **Database**
- SSL enforced for external connections
- Password authentication
- Connection pooling via Supabase Pooler

### **Redis**
- Password authentication (`REDIS_PASSWORD`)
- No public network access (Railway private network only)
- Persistent volume encrypted at rest

### **Supabase**
- Row Level Security (RLS) on tables
- JWT tokens for API access
- Service role key for admin operations

---

## 💰 Costs & Plans

### **Current Plan: Trial (Free)**

**Railway**:
- 500 service hours/month
- 1GB outbound data/month
- Shared CPU/RAM
- Automatic sleep after inactivity

**Supabase**:
- Free tier: 500MB database
- 50,000 monthly active users
- 1GB file storage

**Vercel**:
- Hobby tier: 100GB bandwidth
- Serverless functions
- Preview deployments

**OpenRouter**:
- Pay-per-token usage
- Bills based on AI model usage

---

## 🎯 Next Steps

1. **Fix Production API Crash** (CRITICAL)
   - Investigate logs immediately
   - Restart service
   - Redeploy if needed

2. **Add Health Check**
   ```toml
   [deploy]
   healthcheckPath = "/health"
   healthcheckTimeout = 30
   ```

3. **Configure Production CORS**
   - Add Vercel domain to `API_CORS_ALLOWED_ORIGINS`

4. **Set Up Monitoring**
   - Log aggregation
   - Error tracking (Sentry)
   - Uptime monitoring

5. **Consider Upgrading Plans**
   - Railway Pro for dedicated resources
   - Supabase Pro for larger database
   - Vercel Pro for team features

---

## 📞 Service URLs Summary

| Environment | Service | URL | Status |
|------------|---------|-----|--------|
| Production | API | api-production-97ea.up.railway.app | 🔴 CRASHED |
| Production | Worker | worker-production-d952.up.railway.app | 🟢 Running |
| Production | Redis | Internal only | 🟢 Running |
| Staging | API | api-staging-3c02.up.railway.app | 🟢 Running |
| Staging | Worker | worker-staging-d144.up.railway.app | 🟢 Running |
| Staging | Redis | Internal only | 🟢 Running |
| Database | Supabase | wpxmmnttpehmwhokpqms.supabase.co | 🟢 Running |
