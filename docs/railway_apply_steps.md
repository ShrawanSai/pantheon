# Railway Apply Steps (F1/F14)

## Goal
Ensure Railway `api` and `worker` services run the production modules from this repo.

## API Service (`api`)
1. Open Railway -> `api` service -> Settings -> Config-as-code.
2. Set Railway Config File to:
`/railway.api.toml`
3. Ensure deploy start command resolves from file as:
`python -m uvicorn apps.api.app.main:app --host 0.0.0.0 --port $PORT`
4. Redeploy service.

## Worker Service (`worker`)
1. Open Railway -> `worker` service -> Settings -> Config-as-code.
2. Set Railway Config File to:
`/railway.worker.toml`
3. Ensure deploy start command resolves from file as:
`python -m arq apps.api.app.workers.arq_worker.WorkerSettings`
4. Redeploy service.

## Verify
1. API health route:
`https://api-production-97ea.up.railway.app/api/v1/health`
Expected: `200`
2. API auth route:
`https://api-production-97ea.up.railway.app/api/v1/auth/me` with bearer token
Expected: `200` for valid token, `401` for missing/invalid token.
3. Worker logs should show:
- worker startup banner
- registered function: `health_ping`

## Notes
- If Railway UI shows command overrides, remove manual overrides and keep config-as-code as source of truth.
- F14 is closed once `/api/v1/auth/me` is no longer `404` in deployed API.
