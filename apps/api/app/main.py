from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.app.api.v1.routes.auth import router as auth_router
from apps.api.app.api.v1.routes.health import router as health_router
from apps.api.app.core.config import get_settings


def create_app() -> FastAPI:
    app = FastAPI(title="Pantheon API", version="0.1.0")
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
    return app


app = create_app()
