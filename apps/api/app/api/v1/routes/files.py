from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from apps.api.app.core.config import Settings, get_settings
from apps.api.app.db.models import UploadedFile
from apps.api.app.db.session import get_db
from apps.api.app.dependencies.arq import get_arq_redis
from apps.api.app.dependencies.auth import get_current_user
from apps.api.app.dependencies.rooms import get_owned_active_room_or_404
from apps.api.app.schemas.files import UploadedFileRead
from apps.api.app.services.storage.supabase_storage import StorageService, get_storage_service
from apps.api.app.api.v1.routes.sessions import _get_owned_active_session_or_404
from apps.api.app.workers.jobs.file_parse import _extract_parsed_text

import logging
_LOGGER = logging.getLogger(__name__)

router = APIRouter(tags=["files"])

ALLOWED_FILE_EXTENSIONS = {"txt", "md", "csv", "pdf", "docx", "xlsx", "xls"}


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
    "/rooms/{room_id}/files",
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
        raise HTTPException(status_code=422, detail="Unsupported file format. Allowed: txt, md, csv, pdf, docx, xlsx, xls.")

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

    # Try inline parsing first (arq worker may not be running)
    try:
        parsed_text = _extract_parsed_text(filename, payload)
        file_row.parse_status = "completed"
        file_row.parsed_text = parsed_text
        file_row.error_message = None
        await db.commit()
        await db.refresh(file_row)
    except Exception as e:
        _LOGGER.warning("Inline parse failed for %s: %s", filename, e, exc_info=True)
        try:
            await arq_redis.enqueue_job("file_parse", file_row.id)
        except Exception as arq_err:
            _LOGGER.warning("arq enqueue also failed for file %s: %s", file_row.id, arq_err)
            file_row.parse_status = "failed"
            file_row.error_message = f"Inline parse error: {e}"
            await db.commit()
            await db.refresh(file_row)
    return _to_uploaded_file_read(file_row)


@router.get(
    "/rooms/{room_id}/files",
    response_model=list[UploadedFileRead],
)
async def list_room_files(
    room_id: str,
    current_user: dict[str, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[UploadedFileRead]:
    user_id = current_user["user_id"]
    await get_owned_active_room_or_404(db, room_id=room_id, user_id=user_id)

    rows = (
        await db.scalars(
            select(UploadedFile)
            .where(UploadedFile.room_id == room_id)
            .order_by(UploadedFile.created_at.desc())
        )
    ).all()
    return [_to_uploaded_file_read(row) for row in rows]


@router.post(
    "/sessions/{session_id}/files",
    response_model=UploadedFileRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_session_file(
    session_id: str,
    file: UploadFile = File(...),
    current_user: dict[str, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    storage: StorageService = Depends(get_storage_service),
    arq_redis: ArqRedis = Depends(get_arq_redis),
) -> UploadedFileRead:
    user_id = current_user["user_id"]
    await _get_owned_active_session_or_404(db, session_id=session_id, user_id=user_id)

    filename = (file.filename or "").strip()
    if not filename:
        raise HTTPException(status_code=422, detail="Filename is required.")
    extension = Path(filename).suffix.lower().lstrip(".")
    if extension not in ALLOWED_FILE_EXTENSIONS:
        raise HTTPException(status_code=422, detail="Unsupported file format. Allowed: txt, md, csv, pdf, docx, xlsx, xls.")

    payload = await file.read()
    file_size = len(payload)
    if file_size > settings.file_max_bytes:
        raise HTTPException(status_code=413, detail="File exceeds maximum allowed size.")

    file_id = str(uuid4())
    safe_name = Path(filename).name.replace(" ", "_")
    storage_key = f"sessions/{session_id}/{file_id}/{safe_name}"
    content_type = (file.content_type or "application/octet-stream").strip() or "application/octet-stream"

    await storage.upload_bytes(storage_key=storage_key, content=payload, content_type=content_type)

    file_row = UploadedFile(
        id=file_id,
        user_id=user_id,
        room_id=None,
        session_id=session_id,
        filename=filename,
        storage_key=storage_key,
        content_type=content_type,
        file_size=file_size,
    )
    db.add(file_row)
    await db.commit()
    await db.refresh(file_row)

    # Try inline parsing first (arq worker may not be running)
    try:
        parsed_text = _extract_parsed_text(filename, payload)
        file_row.parse_status = "completed"
        file_row.parsed_text = parsed_text
        file_row.error_message = None
        await db.commit()
        await db.refresh(file_row)
    except Exception as e:
        _LOGGER.warning("Inline parse failed for %s: %s", filename, e, exc_info=True)
        try:
            await arq_redis.enqueue_job("file_parse", file_row.id)
        except Exception as arq_err:
            _LOGGER.warning("arq enqueue also failed for file %s: %s", file_row.id, arq_err)
            file_row.parse_status = "failed"
            file_row.error_message = f"Inline parse error: {e}"
            await db.commit()
            await db.refresh(file_row)
    return _to_uploaded_file_read(file_row)


@router.get(
    "/sessions/{session_id}/files",
    response_model=list[UploadedFileRead],
)
async def list_session_files(
    session_id: str,
    current_user: dict[str, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[UploadedFileRead]:
    user_id = current_user["user_id"]
    await _get_owned_active_session_or_404(db, session_id=session_id, user_id=user_id)

    rows = (
        await db.scalars(
            select(UploadedFile)
            .where(UploadedFile.session_id == session_id)
            .order_by(UploadedFile.created_at.desc())
        )
    ).all()
    return [_to_uploaded_file_read(row) for row in rows]

