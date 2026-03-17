---
description: View recent logs from Railway services. Usage: /railway-logs [production|staging] [api|worker]
---

View recent logs from Railway services. This command will:

1. Determine the environment (production or staging) and service (api or worker) from arguments
2. Default to: environment=production, service=api
3. Run: `railway logs --environment <env> --service <service> --limit 50`
4. Display the last 50 log lines
5. Highlight any errors or warnings in red

**Examples:**
- `/railway-logs` - View production API logs
- `/railway-logs production worker` - View production worker logs
- `/railway-logs staging api` - View staging API logs

**Note**: If no Railway CLI is authenticated, remind the user to run `railway login` first.
