"""Catalog import against a real PostgreSQL (requires Docker)."""

import csv
import json
import shutil
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.db import create_engine, create_session_factory
from app.modules.catalog.service import import_catalog, run_import
from app.modules.catalog.sources.tmdb5000_csv import (
    CREDITS_FILE,
    MOVIES_FILE,
    Tmdb5000CsvSource,
)
from app.modules.titles.models import (
    Genre,
    Keyword,
    MediaType,
    MovieDetails,
    Person,
    Title,
    TitleCredit,
    TitleGenre,
    TitleKeyword,
)

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "tmdb5000"
CATALOG_TABLES = (
    "title_credits, people, title_keywords, keywords, title_genres, genres, movie_details, titles"
)

SessionFactory = async_sessionmaker[AsyncSession]


@pytest.fixture
async def session_factory(migrated_db_url: str) -> AsyncIterator[SessionFactory]:
    engine = create_engine(migrated_db_url)
    async with engine.begin() as conn:
        # Disposable test container: start every test from empty catalog tables.
        await conn.execute(text(f"TRUNCATE {CATALOG_TABLES} RESTART IDENTITY"))
    yield create_session_factory(engine)
    await engine.dispose()


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    for name in (MOVIES_FILE, CREDITS_FILE):
        shutil.copy(FIXTURES / name, tmp_path / name)
    return tmp_path


def edit_csv(path: Path, edit: Callable[[list[dict[str, str]]], list[dict[str, str]]]) -> None:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or ())
        rows = list(reader)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(edit(rows))


async def count(factory: SessionFactory, model: type[Any]) -> int:
    async with factory() as session:
        return (await session.execute(select(func.count()).select_from(model))).scalar_one()


async def title_by_tmdb_id(factory: SessionFactory, tmdb_id: int) -> Title:
    async with factory() as session:
        stmt = select(Title).where(Title.media_type == MediaType.MOVIE, Title.tmdb_id == tmdb_id)
        return (await session.execute(stmt)).scalar_one()


async def test_first_import_creates_catalog(session_factory: SessionFactory) -> None:
    report = await import_catalog(session_factory, Tmdb5000CsvSource(FIXTURES))

    assert (report.titles_inserted, report.titles_updated, report.titles_unchanged) == (3, 0, 0)
    assert report.invalid == 3
    assert len(report.changed_title_ids) == 3
    assert await count(session_factory, Title) == 3
    assert await count(session_factory, MovieDetails) == 3
    assert await count(session_factory, Genre) == 3
    assert await count(session_factory, TitleGenre) == 4
    assert await count(session_factory, Keyword) == 2
    assert await count(session_factory, TitleKeyword) == 3
    assert await count(session_factory, Person) == 4  # shared actor and director deduped
    assert await count(session_factory, TitleCredit) == 6  # Sound Editor skipped

    alpha = await title_by_tmdb_id(session_factory, 100)
    assert alpha.slug == "alpha-movie"
    assert alpha.imported_at is not None
    brulee = await title_by_tmdb_id(session_factory, 400)
    assert brulee.slug == "creme-brulee"

    async with session_factory() as session:
        genre = (await session.execute(select(Genre).where(Genre.tmdb_id == 18))).scalar_one()
        beta_details = await session.get(
            MovieDetails, (await title_by_tmdb_id(session_factory, 200)).id
        )
    assert (genre.slug, genre.media_types) == ("drama", [MediaType.MOVIE])
    assert beta_details is not None
    assert (beta_details.runtime, beta_details.budget, beta_details.revenue) == (None, None, None)


async def test_reimport_of_unchanged_data_writes_nothing(session_factory: SessionFactory) -> None:
    await import_catalog(session_factory, Tmdb5000CsvSource(FIXTURES))
    before = await title_by_tmdb_id(session_factory, 100)

    report = await import_catalog(session_factory, Tmdb5000CsvSource(FIXTURES))

    assert (report.titles_inserted, report.titles_updated, report.titles_unchanged) == (0, 0, 3)
    assert report.changed_title_ids == []
    after = await title_by_tmdb_id(session_factory, 100)
    assert (after.updated_at, after.imported_at) == (before.updated_at, before.imported_at)
    assert await count(session_factory, TitleCredit) == 6


async def test_changes_update_in_place(session_factory: SessionFactory, data_dir: Path) -> None:
    await import_catalog(session_factory, Tmdb5000CsvSource(data_dir))
    alpha_before = await title_by_tmdb_id(session_factory, 100)
    beta = await title_by_tmdb_id(session_factory, 200)

    def new_overview(rows: list[dict[str, str]]) -> list[dict[str, str]]:
        for row in rows:
            if row["id"] == "100":
                row["overview"] = "A rewritten overview."
        return rows

    def new_character(rows: list[dict[str, str]]) -> list[dict[str, str]]:
        for row in rows:
            if row["movie_id"] == "200":
                cast = json.loads(row["cast"])
                cast[0]["character"] = "Hero, Older"
                row["cast"] = json.dumps(cast)
        return rows

    edit_csv(data_dir / MOVIES_FILE, new_overview)
    edit_csv(data_dir / CREDITS_FILE, new_character)
    report = await import_catalog(session_factory, Tmdb5000CsvSource(data_dir))

    # Alpha: title row changed. Beta: only a credit changed. Brulee: untouched.
    assert (report.titles_inserted, report.titles_updated, report.titles_unchanged) == (0, 2, 1)
    assert report.changed_title_ids == sorted([alpha_before.id, beta.id])
    alpha_after = await title_by_tmdb_id(session_factory, 100)
    assert alpha_after.id == alpha_before.id
    assert alpha_after.overview == "A rewritten overview."
    assert alpha_after.updated_at > alpha_before.updated_at
    async with session_factory() as session:
        characters = (
            await session.execute(
                select(TitleCredit.character).where(TitleCredit.tmdb_credit_id == "c200a")
            )
        ).scalar_one()
    assert characters == "Hero, Older"
    assert await count(session_factory, TitleCredit) == 6


async def test_rows_missing_from_source_are_not_deleted(
    session_factory: SessionFactory, data_dir: Path
) -> None:
    await import_catalog(session_factory, Tmdb5000CsvSource(data_dir))
    edit_csv(data_dir / MOVIES_FILE, lambda rows: [r for r in rows if r["id"] != "400"])

    report = await import_catalog(session_factory, Tmdb5000CsvSource(data_dir))

    assert report.titles_unchanged == 2
    assert await count(session_factory, Title) == 3


async def test_reimport_keeps_columns_the_source_does_not_provide(
    session_factory: SessionFactory, data_dir: Path
) -> None:
    await import_catalog(session_factory, Tmdb5000CsvSource(data_dir))
    async with session_factory() as session, session.begin():
        await session.execute(
            update(Title).where(Title.tmdb_id == 100).values(poster_path="/alpha.jpg")
        )

    def change_title(rows: list[dict[str, str]]) -> list[dict[str, str]]:
        for row in rows:
            if row["id"] == "100":
                row["tagline"] = "Go further."
        return rows

    edit_csv(data_dir / MOVIES_FILE, change_title)
    await import_catalog(session_factory, Tmdb5000CsvSource(data_dir))

    alpha = await title_by_tmdb_id(session_factory, 100)
    assert alpha.tagline == "Go further."
    assert alpha.poster_path == "/alpha.jpg"


async def test_small_batches_give_the_same_result(session_factory: SessionFactory) -> None:
    report = await import_catalog(session_factory, Tmdb5000CsvSource(FIXTURES), batch_size=1)

    assert report.titles_inserted == 3
    assert await count(session_factory, Person) == 4
    assert await count(session_factory, TitleCredit) == 6


async def test_run_import_reads_catalog_data_dir_setting(
    session_factory: SessionFactory, migrated_db_url: str
) -> None:
    settings = Settings(app_env="test", database_url=migrated_db_url, catalog_data_dir=FIXTURES)

    report = await run_import(settings)

    assert (report.source, report.titles_inserted) == ("tmdb5000_csv", 3)
