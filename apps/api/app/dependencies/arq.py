from __future__ import annotations

from arq.connections import ArqRedis
from fastapi import HTTPException, Request


def get_arq_redis(request: Request) -> ArqRedis:
    redis_pool = getattr(request.app.state, "arq_redis", None)
    if redis_pool is None:
        raise HTTPException(status_code=503, detail="Background queue is unavailable.")
    return redis_pool

