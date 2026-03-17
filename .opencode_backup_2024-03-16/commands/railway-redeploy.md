---
description: Redeploy a Railway service from a specific commit or last successful deployment. Usage: /railway-redeploy [production|staging] [api|worker]
---

Redeploy a Railway service. This command will:

1. Determine the environment and service from arguments
2. Default to: environment=production, service=api
3. Run: `railway redeploy --environment <env> --service <service>`
4. Show the deployment progress
5. Confirm when deployment completes

**Examples:**
- `/railway-redeploy` - Redeploy production API
- `/railway-redeploy production worker` - Redeploy production worker
- `/railway-redeploy staging api` - Redeploy staging API

**Note**: This triggers a new deployment using the same commit as the last deployment. To deploy a different commit, push new code to the repository first.
