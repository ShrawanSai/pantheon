---
description: Restart a Railway service. Usage: /railway-restart [production|staging] [api|worker]
---

Restart a Railway service. This command will:

1. Determine the environment (production or staging) and service (api or worker) from arguments
2. Default to: environment=production, service=api
3. Run: `railway restart --environment <env> --service <service>`
4. Confirm the restart was triggered
5. Wait 10 seconds, then check the service status again

**Examples:**
- `/railway-restart` - Restart production API
- `/railway-restart production worker` - Restart production worker
- `/railway-restart staging api` - Restart staging API

**Note**: Only use this to recover from crashed or stuck services. For code changes, redeploy instead.
