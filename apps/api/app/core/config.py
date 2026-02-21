from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_anon_key: str | None
    supabase_service_role_key: str


def get_settings() -> Settings:
    supabase_url = os.getenv("SUPABASE_URL")
    if not supabase_url:
        raise RuntimeError("SUPABASE_URL must be set.")
    supabase_service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_service_role_key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY must be set.")
    return Settings(
        supabase_url=supabase_url,
        supabase_anon_key=os.getenv("SUPABASE_ANON_KEY"),
        supabase_service_role_key=supabase_service_role_key,
    )
