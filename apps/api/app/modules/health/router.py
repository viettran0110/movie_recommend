from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.modules.health.schemas import HealthResponse
from app.modules.health.service import (
    HealthCheck,
    database_check,
    meilisearch_check,
    redis_check,
    run_checks,
)

router = APIRouter(tags=["health"])


def get_health_checks(request: Request) -> dict[str, HealthCheck]:
    state = request.app.state
    return {
        "database": database_check(state.engine),
        "redis": redis_check(state.redis),
        "meilisearch": meilisearch_check(state.http, state.settings.meili_url),
    }


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse}},
)
async def health(
    response: Response,
    checks: Annotated[dict[str, HealthCheck], Depends(get_health_checks)],
) -> HealthResponse:
    results = await run_checks(checks)
    healthy = all(results.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(status="ok" if healthy else "degraded", checks=results)
