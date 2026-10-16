import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping

import httpx
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

HealthCheck = Callable[[], Awaitable[None]]

CHECK_TIMEOUT_SECONDS = 2.0


def database_check(engine: AsyncEngine) -> HealthCheck:
    async def check() -> None:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    return check


def redis_check(redis: Redis) -> HealthCheck:
    async def check() -> None:
        await redis.ping()

    return check


def meilisearch_check(http: httpx.AsyncClient, meili_url: str) -> HealthCheck:
    async def check() -> None:
        response = await http.get(f"{meili_url.rstrip('/')}/health")
        response.raise_for_status()

    return check


async def run_checks(checks: Mapping[str, HealthCheck]) -> dict[str, bool]:
    async def run_one(name: str, check: HealthCheck) -> bool:
        try:
            await asyncio.wait_for(check(), timeout=CHECK_TIMEOUT_SECONDS)
        except Exception:
            # Log the failure type only; connection errors can embed DSNs with credentials.
            logger.warning("health check failed: %s", name, exc_info=False)
            return False
        return True

    names = list(checks)
    results = await asyncio.gather(*(run_one(name, checks[name]) for name in names))
    return dict(zip(names, results, strict=True))
