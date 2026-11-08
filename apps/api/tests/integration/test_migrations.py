"""Migration round-trip against a real PostgreSQL + pgvector (requires Docker)."""

import asyncio
from typing import Any

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Connection, text
from testcontainers.community.postgres import PostgresContainer

import app.modules.titles.models  # noqa: F401  (registers tables on Base.metadata)
from app.core.db import Base, create_engine
from tests.integration.db import alembic_config

pytestmark = pytest.mark.integration

EXTENSIONS = {"vector", "pg_trgm", "citext"}
CATALOG_TABLES = {
    "titles",
    "movie_details",
    "genres",
    "title_genres",
    "keywords",
    "title_keywords",
    "people",
    "title_credits",
}
ENUMS = {"media_type", "title_status", "credit_role"}


def query_set(url: str, sql: str) -> set[str]:
    async def run() -> set[str]:
        engine = create_engine(url)
        async with engine.connect() as conn:
            names = {row[0] for row in await conn.execute(text(sql))}
        await engine.dispose()
        return names

    return asyncio.run(run())


def installed_extensions(url: str) -> set[str]:
    return query_set(url, "SELECT extname FROM pg_extension")


def public_tables(url: str) -> set[str]:
    return query_set(url, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")


def enum_types(url: str) -> set[str]:
    return query_set(url, "SELECT typname FROM pg_type WHERE typtype = 'e'")


def schema_diff(url: str) -> list[Any]:
    def compare(conn: Connection) -> list[Any]:
        context = MigrationContext.configure(conn, opts={"compare_type": True})
        return list(compare_metadata(context, Base.metadata))

    async def run() -> list[Any]:
        engine = create_engine(url)
        async with engine.connect() as conn:
            diff = await conn.run_sync(compare)
        await engine.dispose()
        return diff

    return asyncio.run(run())


def assert_at_head(url: str) -> None:
    assert installed_extensions(url) >= EXTENSIONS
    assert public_tables(url) >= CATALOG_TABLES
    assert enum_types(url) >= ENUMS


def test_upgrade_downgrade_upgrade(postgres: PostgresContainer) -> None:
    url = postgres.get_connection_url()
    config = alembic_config(url)

    command.upgrade(config, "head")
    assert_at_head(url)

    command.downgrade(config, "base")
    assert not installed_extensions(url) & EXTENSIONS
    assert not public_tables(url) & CATALOG_TABLES
    assert not enum_types(url) & ENUMS

    command.upgrade(config, "head")
    assert_at_head(url)


def test_migrations_match_models(postgres: PostgresContainer) -> None:
    url = postgres.get_connection_url()
    command.upgrade(alembic_config(url), "head")

    # Hand-written migrations must produce exactly what the ORM models declare.
    assert schema_diff(url) == []
