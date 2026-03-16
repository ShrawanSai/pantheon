---
description: Check Railway deployment status for all services (production & staging)
---

Check the deployment status of all Railway services. This command will:

1. Show project information (name, ID, workspace)
2. List all environments (production, staging)
3. For each environment, show:
   - API service status, URL, and last deployment info
   - Worker service status, URL, and last deployment info
   - Redis service status
4. Highlight any crashed or failed deployments
5. Show recent deployment history

Use this to quickly assess the health of your infrastructure before pushing changes or when troubleshooting issues.

**Example output includes:**
- Service status (RUNNING, CRASHED, DEPLOYING)
- Deployment IDs and commit messages
- URLs for accessing services
- Any errors or warnings

**Note**: If services show as CRASHED, use `/railway-logs` or `/railway-restart` commands to investigate and fix.
