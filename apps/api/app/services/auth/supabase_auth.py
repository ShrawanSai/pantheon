from __future__ import annotations

from typing import Any

from supabase import create_client

from apps.api.app.core.config import get_settings


def verify_supabase_bearer_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    result = client.auth.get_user(token)
    user = getattr(result, "user", None)
    if user is None:
        raise ValueError("Invalid or expired token.")
    return {
        "id": str(user.id),
        "email": user.email,
    }
