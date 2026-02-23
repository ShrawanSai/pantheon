# Enforcement Rollout Runbook

## Default State
- `CREDIT_ENFORCEMENT_ENABLED` defaults to `false`.
- Environments are warn-only by default (turns are not blocked for depleted balance).

## Enable Enforcement

### Option A: Startup Config (persistent)
1. Set `CREDIT_ENFORCEMENT_ENABLED=true`.
2. Restart/redeploy API.
3. Effective behavior remains enabled across process restarts.

### Option B: Runtime Override (no restart)
1. Call:

```http
PATCH /api/v1/admin/settings/enforcement
Content-Type: application/json
Authorization: Bearer <admin-token>

{"enabled": true}
```

2. This applies immediately in-memory.
3. This override does **not** survive process restart.

## Verify Enforcement State
1. Call:

```http
GET /api/v1/admin/settings
Authorization: Bearer <admin-token>
```

2. Verify response fields:
- `enforcement_enabled` (`true`/`false`) = effective state
- `enforcement_source` (`override` or `config`) = where effective value comes from

Optional: `GET /api/v1/health` for basic liveness only.

## Rollback

### Runtime Rollback (without restart)
1. Call:

```http
DELETE /api/v1/admin/settings/enforcement
Authorization: Bearer <admin-token>
```

2. Override is cleared.
3. Effective state falls back to env config (`CREDIT_ENFORCEMENT_ENABLED`).

### Full Rollback (persistent)
1. Set `CREDIT_ENFORCEMENT_ENABLED=false`.
2. Restart/redeploy API.
3. Service is guaranteed warn-only after startup.

## Effective Behavior Matrix

| `CREDIT_ENFORCEMENT_ENABLED` (env) | In-memory override | Effective | Source |
|---|---|---|---|
| `false` | `None` | `false` | `config` |
| `true` | `None` | `true` | `config` |
| `false` | `true` | `true` | `override` |
| `true` | `false` | `false` | `override` |

## Admin API Quick Reference

### `GET /api/v1/admin/settings`
- Purpose: read effective runtime settings snapshot.
- Response:

```json
{
  "enforcement_enabled": false,
  "enforcement_source": "config",
  "low_balance_threshold": 5.0,
  "pricing_version": "2026-02-20"
}
```

### `PATCH /api/v1/admin/settings/enforcement`
- Purpose: set in-memory enforcement override.
- Request:

```json
{"enabled": true}
```

- Response:

```json
{"enforcement_enabled": true, "source": "override"}
```

### `DELETE /api/v1/admin/settings/enforcement`
- Purpose: clear in-memory override and revert to config source.
- Response:

```json
{"enforcement_enabled": false, "source": "config"}
```
