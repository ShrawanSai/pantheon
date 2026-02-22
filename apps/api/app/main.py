from __future__ import annotations

import inspect
import logging
from contextlib import asynccontextmanager

from arq import create_pool
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.app.api.v1.routes.auth import router as auth_router
from apps.api.app.api.v1.routes.admin import router as admin_router
from apps.api.app.api.v1.routes.files import router as files_router
from apps.api.app.api.v1.routes.health import router as health_router
from apps.api.app.api.v1.routes.rooms import router as rooms_router
from apps.api.app.api.v1.routes.sessions import router as sessions_router
from apps.api.app.api.v1.routes.users import router as users_router
from apps.api.app.core.config import get_settings
from apps.api.app.workers.arq_worker import redis_settings_from_env

_LOGGER = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    app.state.arq_redis = None
    try:
        redis_settings = redis_settings_from_env()
    except RuntimeError as exc:
        _LOGGER.warning("ARQ pool startup skipped: %s", exc)
    else:
        app.state.arq_redis = await create_pool(redis_settings)
    try:
        yield
    finally:
        redis_pool = getattr(app.state, "arq_redis", None)
        if redis_pool is not None:
            aclose = getattr(redis_pool, "aclose", None)
            if callable(aclose):
                await aclose()
            else:
                close = getattr(redis_pool, "close", None)
                if callable(close):
                    maybe_awaitable = close()
                    if inspect.isawaitable(maybe_awaitable):
                        await maybe_awaitable


def create_app() -> FastAPI:
    app = FastAPI(title="Pantheon API", version="0.1.0", lifespan=_lifespan)
    settings = get_settings()
    if settings.api_cors_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.api_cors_allowed_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(admin_router, prefix="/api/v1")
    app.include_router(rooms_router, prefix="/api/v1")
    app.include_router(files_router, prefix="/api/v1")
    app.include_router(sessions_router, prefix="/api/v1")
    app.include_router(users_router, prefix="/api/v1")
    return app


app = create_app()
