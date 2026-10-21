import os

# Must be set before app modules read settings (broker selection, etc.).
os.environ["APP_ENV"] = "test"

from collections.abc import AsyncIterator

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def app() -> FastAPI:
    return create_app(Settings(app_env="test"))


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with LifespanManager(app) as manager:
        transport = httpx.ASGITransport(app=manager.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
