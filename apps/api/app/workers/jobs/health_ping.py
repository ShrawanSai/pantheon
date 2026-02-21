from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


async def health_ping(ctx: dict[str, Any], payload: str = "ping") -> dict[str, str]:
    return {
        "status": "ok",
        "payload": payload,
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }

