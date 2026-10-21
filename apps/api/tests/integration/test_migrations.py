"""Migration round-trip against a real PostgreSQL + pgvector (requires Docker)."""

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from testcontainers.community.postgres import PostgresContainer

from app.core.db import create_engine

pytestmark = pytest.mark.integration

API_ROOT = Path(__file__).resolve().parents[2]
PG_IMAGE = "pgvector/pgvector:0.8.7-pg17"  # keep in sync with infra/docker-compose.yml


@pytest.fixture(scope="module")
def postgres() -> Iterator[PostgresContainer]:
    with PostgresContainer(PG_IMAGE, driver="asyncpg") as container:
        yield container


def alembic_config(url: str) -> Config:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url)
    config.attributes["configure_logger"] = False
    return config


def installed_extensions(url: str) -> set[str]:
    async def query() -> set[str]:
        engine = create_engine(url)
        async with engine.connect() as conn:
            rows = await conn.execute(text("SELECT extname FROM pg_extension"))
            names = {row[0] for row in rows}
        await engine.dispose()
        return names

    return asyncio.run(query())


def test_upgrade_downgrade_upgrade(postgres: PostgresContainer) -> None:
    url = postgres.get_connection_url()
    config = alembic_config(url)

    command.upgrade(config, "head")
    assert {"vector", "pg_trgm", "citext"} <= installed_extensions(url)

    command.downgrade(config, "base")
    assert not {"vector", "pg_trgm", "citext"} & installed_extensions(url)

    command.upgrade(config, "head")
    assert {"vector", "pg_trgm", "citext"} <= installed_extensions(url)
