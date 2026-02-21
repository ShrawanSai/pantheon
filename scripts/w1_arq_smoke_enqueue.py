from __future__ import annotations

import asyncio
import os

from arq.connections import RedisSettings, create_pool
from dotenv import load_dotenv

load_dotenv()


async def main() -> None:
    redis_dsn = os.getenv("REDIS_URL")
    if not redis_dsn:
        raise RuntimeError("REDIS_URL is required for arq smoke enqueue.")

    redis = await create_pool(RedisSettings.from_dsn(redis_dsn))
    job = await redis.enqueue_job("health_ping", "week1-smoke")
    print(f"enqueued_job_id={job.job_id}")
    await redis.close()


if __name__ == "__main__":
    asyncio.run(main())
