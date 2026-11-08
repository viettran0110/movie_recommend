from collections.abc import Iterator

import pytest
from alembic import command
from testcontainers.community.postgres import PostgresContainer

from tests.integration.db import PG_IMAGE, alembic_config


@pytest.fixture(scope="module")
def postgres() -> Iterator[PostgresContainer]:
    """A fresh, empty database per test module."""
    with PostgresContainer(PG_IMAGE, driver="asyncpg") as container:
        yield container


@pytest.fixture(scope="module")
def migrated_db_url(postgres: PostgresContainer) -> str:
    url = postgres.get_connection_url()
    command.upgrade(alembic_config(url), "head")
    return url
