"""The error envelope, without a database (api-contracts.md "Errors")."""

import httpx
import pytest
from fastapi import FastAPI

from app.core.errors import NotFoundError


async def test_unknown_route_uses_error_envelope(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/no-such-route")

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "Not Found", "details": {}}
    }


async def test_wrong_method_uses_error_envelope(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/v1/health")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"
    assert "allow" in response.headers


@pytest.mark.parametrize("path", ["/api/v1/titles/abc", "/api/v1/titles/0"])
async def test_validation_error_lists_fields_without_echoing_input(
    client: httpx.AsyncClient, path: str
) -> None:
    response = await client.get(path)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["message"] == "Request validation failed"
    [field] = error["details"]["errors"]
    assert field["loc"] == ["path", "title_id"]
    assert set(field) == {"loc", "msg", "type"}


async def test_app_error_maps_to_status_and_envelope(app: FastAPI) -> None:
    @app.get("/boom")
    async def boom() -> None:
        raise NotFoundError("Thing not found", {"thing_id": 7})

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/boom")

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "Thing not found", "details": {"thing_id": 7}}
    }
