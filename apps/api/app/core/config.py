from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_anon_key: str | None
    supabase_service_role_key: str
    api_cors_allowed_origins: list[str]
    openrouter_api_key: str | None
    openrouter_base_url: str
    context_max_output_tokens: int
    context_summary_trigger_ratio: float
    context_prune_trigger_ratio: float
    context_mandatory_summary_turn: int
    context_default_model_limit: int
    context_recent_turns_to_keep: int
    pricing_version: str


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer.") from exc


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a float.") from exc


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    supabase_url = os.getenv("SUPABASE_URL")
    if not supabase_url:
        raise RuntimeError("SUPABASE_URL must be set.")
    supabase_service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_service_role_key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY must be set.")
    raw_origins = os.getenv("API_CORS_ALLOWED_ORIGINS", "")
    api_cors_allowed_origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]

    return Settings(
        supabase_url=supabase_url,
        supabase_anon_key=os.getenv("SUPABASE_ANON_KEY"),
        supabase_service_role_key=supabase_service_role_key,
        api_cors_allowed_origins=api_cors_allowed_origins,
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY"),
        openrouter_base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/"),
        context_max_output_tokens=_int_env("CONTEXT_MAX_OUTPUT_TOKENS", 2048),
        context_summary_trigger_ratio=_float_env("CONTEXT_SUMMARY_TRIGGER_RATIO", 0.70),
        context_prune_trigger_ratio=_float_env("CONTEXT_PRUNE_TRIGGER_RATIO", 0.90),
        context_mandatory_summary_turn=_int_env("CONTEXT_MANDATORY_SUMMARY_TURN", 8),
        context_default_model_limit=_int_env("CONTEXT_DEFAULT_MODEL_LIMIT", 8192),
        context_recent_turns_to_keep=_int_env("CONTEXT_RECENT_TURNS_TO_KEEP", 4),
        pricing_version=os.getenv("PRICING_VERSION", "2026-02-20"),
    )
