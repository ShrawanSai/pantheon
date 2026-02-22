from __future__ import annotations

import os

from arq.connections import RedisSettings
from dotenv import load_dotenv

from apps.api.app.workers.jobs.file_parse import file_parse
from apps.api.app.workers.jobs.health_ping import health_ping

load_dotenv()


def redis_settings_from_env() -> RedisSettings:
    redis_dsn = os.getenv("REDIS_URL")
    if not redis_dsn:
        raise RuntimeError("REDIS_URL must be set for arq worker startup.")
    return RedisSettings.from_dsn(redis_dsn)


class _LazyRedisSettings:
    """Resolve RedisSettings only when arq actually accesses settings fields."""

    def __init__(self) -> None:
        self._resolved: RedisSettings | None = None

    def _get(self) -> RedisSettings:
        if self._resolved is None:
            self._resolved = redis_settings_from_env()
        return self._resolved

    def __getattr__(self, item: str):
        return getattr(self._get(), item)


class WorkerSettings:
    functions = [health_ping, file_parse]
    job_timeout = 30
    keep_result = 60
    redis_settings = _LazyRedisSettings()
