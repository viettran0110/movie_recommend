import asyncio

import httpx
import pytest
from fastapi import FastAPI

from app.modules.health import service
from app.modules.health.router import get_health_checks
from app.modules.health.service import HealthCheck


async def ok() -> None:
    return None


async def fail() -> None:
    raise ConnectionError("postgresql://user:secret@db/movie unreachable")


async def hang() -> None:
    await asyncio.sleep(10)


def override(app: FastAPI, checks: dict[str, HealthCheck]) -> None:
    app.dependency_overrides[get_health_checks] = lambda: checks


async def test_health_ok(app: FastAPI, client: httpx.AsyncClient) -> None:
    override(app, {"database": ok, "redis": ok, "meilisearch": ok})

    response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"database": True, "redis": True, "meilisearch": True},
    }


async def test_health_degraded_when_a_dependency_fails(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    override(app, {"database": fail, "redis": ok, "meilisearch": ok})

    response = await client.get("/api/v1/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["database"] is False
    assert "secret" not in response.text


async def test_health_check_times_out(
    app: FastAPI, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(service, "CHECK_TIMEOUT_SECONDS", 0.05)
    override(app, {"database": ok, "redis": hang, "meilisearch": ok})

    response = await client.get("/api/v1/health")

    assert response.status_code == 503
    assert response.json()["checks"]["redis"] is False
