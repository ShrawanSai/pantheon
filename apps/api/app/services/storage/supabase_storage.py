from __future__ import annotations

import asyncio
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
    def __init__(self) -> None:
        settings = get_settings()
        self._bucket = settings.supabase_storage_bucket
        self._client = create_client(settings.supabase_url, settings.supabase_service_role_key)

    async def upload_bytes(
        self,
        *,
        storage_key: str,
        content: bytes,
        content_type: str,
    ) -> None:
        upload_fn = self._client.storage.from_(self._bucket).upload
        # TODO: replace thread-offload with async storage client when traffic scales.
        await asyncio.to_thread(
            upload_fn,
            storage_key,
            content,
            {"content-type": content_type, "upsert": "false"},
        )


_storage_service: StorageService | None = None


def get_storage_service() -> StorageService:
    global _storage_service
    if _storage_service is None:
        _storage_service = SupabaseStorageService()
    return _storage_service
