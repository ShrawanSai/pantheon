from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.core.config import Settings, get_settings
from apps.api.app.db.models import UploadedFile
from apps.api.app.db.session import get_db
from apps.api.app.dependencies.arq import get_arq_redis
from apps.api.app.dependencies.auth import get_current_user
from apps.api.app.dependencies.rooms import get_owned_active_room_or_404
from apps.api.app.schemas.files import UploadedFileRead
from apps.api.app.services.storage.supabase_storage import StorageService, get_storage_service

router = APIRouter(prefix="/rooms", tags=["files"])

ALLOWED_FILE_EXTENSIONS = {"txt", "md", "csv"}


def _build_storage_key(*, room_id: str, file_id: str, filename: str) -> str:
    safe_name = Path(filename).name.replace(" ", "_")
    return f"rooms/{room_id}/{file_id}/{safe_name}"


def _to_uploaded_file_read(file_row: UploadedFile) -> UploadedFileRead:
    return UploadedFileRead(
        id=file_row.id,
        user_id=file_row.user_id,
        room_id=file_row.room_id,
        filename=file_row.filename,
        storage_key=file_row.storage_key,
        content_type=file_row.content_type,
        file_size=file_row.file_size,
        parse_status=file_row.parse_status,
        parsed_text=file_row.parsed_text,
        error_message=file_row.error_message,
        created_at=file_row.created_at,
    )


@router.post(
    "/{room_id}/files",
    response_model=UploadedFileRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_room_file(
    room_id: str,
    file: UploadFile = File(...),
    current_user: dict[str, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    storage: StorageService = Depends(get_storage_service),
    arq_redis: ArqRedis = Depends(get_arq_redis),
) -> UploadedFileRead:
    user_id = current_user["user_id"]
    await get_owned_active_room_or_404(db, room_id=room_id, user_id=user_id)

    filename = (file.filename or "").strip()
    if not filename:
        raise HTTPException(status_code=422, detail="Filename is required.")
    extension = Path(filename).suffix.lower().lstrip(".")
    if extension not in ALLOWED_FILE_EXTENSIONS:
        raise HTTPException(status_code=422, detail="Unsupported file format. Allowed: txt, md, csv.")

    payload = await file.read()
    file_size = len(payload)
    if file_size > settings.file_max_bytes:
        raise HTTPException(status_code=413, detail="File exceeds maximum allowed size.")

    file_id = str(uuid4())
    storage_key = _build_storage_key(room_id=room_id, file_id=file_id, filename=filename)
    content_type = (file.content_type or "application/octet-stream").strip() or "application/octet-stream"

    await storage.upload_bytes(storage_key=storage_key, content=payload, content_type=content_type)

    file_row = UploadedFile(
        id=file_id,
        user_id=user_id,
        room_id=room_id,
        filename=filename,
        storage_key=storage_key,
        content_type=content_type,
        file_size=file_size,
    )
    db.add(file_row)
    await db.commit()
    await db.refresh(file_row)

    await arq_redis.enqueue_job("file_parse", file_row.id)
    return _to_uploaded_file_read(file_row)

