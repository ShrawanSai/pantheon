from __future__ import annotations

from fastapi import APIRouter, Depends

from apps.api.app.dependencies.auth import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me")
def auth_me(current_user: dict[str, str] = Depends(get_current_user)) -> dict[str, str]:
    return current_user
