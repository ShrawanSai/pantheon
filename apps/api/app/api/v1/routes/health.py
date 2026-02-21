from fastapi import APIRouter

from pantheon_app.graph_engine import ChatGraphEngine

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/graph-check")
def graph_check() -> dict[str, bool]:
    # Week 1 carry-forward check: production module can import existing graph engine.
    engine = ChatGraphEngine()
    return {"engine_import_ok": bool(engine)}
