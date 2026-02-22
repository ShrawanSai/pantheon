from __future__ import annotations

from typing import Protocol

from supabase import create_client

from apps.api.app.core.config import get_settings


class StorageService(Protocol):
    async def upload_bytes(
        self,
        *,
        storage_key: str,
        content: bytes,
        content_type: str,
    ) -> None: ...


class SupabaseStorageService:
    async def upload_bytes(
        self,
        *,
        storage_key: str,
        content: bytes,
        content_type: str,
    ) -> None:
        settings = get_settings()
        client = create_client(settings.supabase_url, settings.supabase_service_role_key)
        client.storage.from_(settings.supabase_storage_bucket).upload(
            storage_key,
            content,
            {"content-type": content_type, "upsert": "false"},
        )


_storage_service: StorageService = SupabaseStorageService()


def get_storage_service() -> StorageService:
    return _storage_service

