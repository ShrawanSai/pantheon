from __future__ import annotations

import os

from fastapi import Header, HTTPException

from apps.api.app.core.config import get_settings
from apps.api.app.services.auth.supabase_auth import verify_supabase_bearer_token

# Evaluate once at module load time — not on every request.
# Defaults to "production" if ENVIRONMENT is unset, which disables all bypasses.
_IS_DEVELOPMENT = os.getenv("ENVIRONMENT", "production") == "development"


def get_current_user(authorization: str | None = Header(default=None)) -> dict[str, str]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token.")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing Bearer token.")

    # Dev bypass tokens are only active when ENVIRONMENT=development.
    # In staging or production, these tokens are treated as invalid and rejected normally.
    if _IS_DEVELOPMENT:
        if token == "dev-override":
            return {"user_id": "00000000-0000-0000-0000-000000000001", "email": "devtest@localhost.invalid"}
        if token == "admin-override":
            settings = get_settings()
            admin_id = next(iter(settings.admin_user_ids), "00000000-0000-0000-0000-000000000001")
            return {"user_id": admin_id, "email": "admin@localhost.invalid"}

    try:
        user = verify_supabase_bearer_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Auth verification failed: {exc}") from exc
    return {"user_id": user["id"], "email": user.get("email") or ""}

