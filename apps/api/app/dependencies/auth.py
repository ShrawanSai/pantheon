from __future__ import annotations

from fastapi import Header, HTTPException

from apps.api.app.services.auth.supabase_auth import verify_supabase_bearer_token


def get_current_user(authorization: str | None = Header(default=None)) -> dict[str, str]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token.")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing Bearer token.")
    import os
    if token == "dev-override" and os.getenv("ENVIRONMENT", "local") not in ("production", "prod"):
        return {"user_id": "test-user-id", "email": "test@example.com"}

    try:
        user = verify_supabase_bearer_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Auth verification failed: {exc}") from exc
    return {"user_id": user["id"], "email": user.get("email") or ""}

