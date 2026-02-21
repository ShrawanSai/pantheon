from fastapi import FastAPI

from apps.api.app.api.v1.routes.auth import router as auth_router
from apps.api.app.api.v1.routes.health import router as health_router


def create_app() -> FastAPI:
    app = FastAPI(title="Pantheon API", version="0.1.0")
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    return app


app = create_app()

