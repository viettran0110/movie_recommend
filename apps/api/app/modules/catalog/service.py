"""Catalog import (ADR-023): CatalogSource -> validated records -> idempotent upserts.

Re-running updates rows in place and never deletes. Invalid source rows are counted and
logged by id, never fatal. Each batch of titles commits in its own transaction, so a
crash keeps finished batches and a re-run completes the rest.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.db import create_engine, create_session_factory
from app.modules.catalog import repository
from app.modules.catalog.repository import Row, unique_by
from app.modules.catalog.schemas import (
    CatalogRecord,
    ImportReport,
    InvalidRecord,
    MovieDetailsRecord,
)
from app.modules.catalog.slugs import slugify
from app.modules.catalog.sources import CatalogSource
from app.modules.catalog.sources.tmdb5000_csv import Tmdb5000CsvSource
from app.modules.titles.models import MediaType

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 500

DetailWriter = Callable[[AsyncSession, Sequence[Row]], Awaitable[set[int]]]


@dataclass(frozen=True)
class _DetailSpec:
    record_type: type[BaseModel]
    write: DetailWriter


# One entry per media type (ADR-019). Adding TV means a tv_details table and an entry here.
DETAIL_SPECS: dict[MediaType, _DetailSpec] = {
    MediaType.MOVIE: _DetailSpec(MovieDetailsRecord, repository.upsert_movie_details),
}


@dataclass
class _BatchResult:
    inserted: set[int] = field(default_factory=set)
    updated: set[int] = field(default_factory=set)


def _collect(source: CatalogSource) -> tuple[list[CatalogRecord], list[InvalidRecord]]:
    records: list[CatalogRecord] = []
    invalid: list[InvalidRecord] = []
    for item in source.read():
        if isinstance(item, CatalogRecord):
            records.append(item)
        else:
            invalid.append(item)
    return records, invalid


def _check_details(record: CatalogRecord) -> InvalidRecord | None:
    spec = DETAIL_SPECS.get(record.title.media_type)
    if spec is None:
        return _invalid(record, f"no detail table for media_type {record.title.media_type}")
    if record.details is not None and not isinstance(record.details, spec.record_type):
        return _invalid(record, f"details do not match media_type {record.title.media_type}")
    return None


def _invalid(record: CatalogRecord, error: str) -> InvalidRecord:
    return InvalidRecord(source_id=str(record.title.tmdb_id), error=error)


def _link_rows(other_key: str, pairs: Iterable[tuple[int, int]]) -> list[Row]:
    return [{"title_id": t, other_key: o} for t, o in dict.fromkeys(pairs)]


async def _import_batch(
    session: AsyncSession, batch: Sequence[CatalogRecord], imported_at: datetime
) -> _BatchResult:
    genre_types: dict[int, set[MediaType]] = {}
    genre_rows: dict[int, Row] = {}
    for record in batch:
        for genre in record.genres:
            genre_types.setdefault(genre.tmdb_id, set()).add(record.title.media_type)
            genre_rows[genre.tmdb_id] = {
                "tmdb_id": genre.tmdb_id,
                "name": genre.name,
                "slug": slugify(genre.name),
            }
    for tmdb_id, row in genre_rows.items():
        row["media_types"] = sorted(genre_types[tmdb_id])
    genre_ids = await repository.upsert_genres(session, list(genre_rows.values()))

    keyword_ids = await repository.upsert_keywords(
        session,
        unique_by(
            ({"tmdb_id": k.tmdb_id, "name": k.name} for r in batch for k in r.keywords),
            "tmdb_id",
        ),
    )
    person_ids = await repository.upsert_people(
        session,
        unique_by(
            (
                {"tmdb_id": c.person_tmdb_id, "name": c.person_name}
                for r in batch
                for c in r.credits
            ),
            "tmdb_id",
        ),
    )

    title_rows = [{**r.title.model_dump(), "slug": slugify(r.title.title)} for r in batch]
    title_ids, inserted, updated = await repository.upsert_titles(session, title_rows, imported_at)
    touched: set[int] = set()

    def title_id(record: CatalogRecord) -> int:
        return title_ids[(record.title.media_type, record.title.tmdb_id)]

    for media_type, spec in DETAIL_SPECS.items():
        detail_rows = [
            {"title_id": title_id(r), **r.details.model_dump()}
            for r in batch
            if r.title.media_type == media_type and r.details is not None
        ]
        touched |= await spec.write(session, detail_rows)

    touched |= await repository.link_title_genres(
        session,
        _link_rows(
            "genre_id", ((title_id(r), genre_ids[g.tmdb_id]) for r in batch for g in r.genres)
        ),
    )
    touched |= await repository.link_title_keywords(
        session,
        _link_rows(
            "keyword_id",
            ((title_id(r), keyword_ids[k.tmdb_id]) for r in batch for k in r.keywords),
        ),
    )
    touched |= await repository.upsert_credits(
        session,
        unique_by(
            (
                {
                    "tmdb_credit_id": c.tmdb_credit_id,
                    "title_id": title_id(r),
                    "person_id": person_ids[c.person_tmdb_id],
                    "role": c.role,
                    "job": c.job,
                    "character": c.character,
                    "sort_order": c.sort_order,
                }
                for r in batch
                for c in r.credits
            ),
            "tmdb_credit_id",
        ),
    )
    return _BatchResult(inserted=inserted, updated=(updated | touched) - inserted)


async def import_catalog(
    session_factory: async_sessionmaker[AsyncSession],
    source: CatalogSource,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> ImportReport:
    # Sources do blocking file or network I/O; keep it off the event loop.
    records, invalid = await asyncio.to_thread(_collect, source)

    valid: list[CatalogRecord] = []
    seen: set[tuple[MediaType, int]] = set()
    for record in records:
        key = (record.title.media_type, record.title.tmdb_id)
        problem = _check_details(record) or (
            _invalid(record, "duplicate title") if key in seen else None
        )
        if problem is None:
            seen.add(key)
            valid.append(record)
        else:
            invalid.append(problem)
    for item in invalid:
        logger.warning(
            "invalid catalog row %s from %s: %s", item.source_id, source.name, item.error
        )

    imported_at = datetime.now(UTC)
    inserted: set[int] = set()
    updated: set[int] = set()
    for start in range(0, len(valid), batch_size):
        async with session_factory() as session, session.begin():
            result = await _import_batch(session, valid[start : start + batch_size], imported_at)
        inserted |= result.inserted
        updated |= result.updated

    report = ImportReport(
        source=source.name,
        titles_inserted=len(inserted),
        titles_updated=len(updated),
        titles_unchanged=len(valid) - len(inserted) - len(updated),
        invalid=len(invalid),
        changed_title_ids=sorted(inserted | updated),
    )
    logger.info(
        "catalog import from %s: %d inserted, %d updated, %d unchanged, %d invalid",
        report.source,
        report.titles_inserted,
        report.titles_updated,
        report.titles_unchanged,
        report.invalid,
    )
    return report


async def run_import(settings: Settings) -> ImportReport:
    """Entry point for the worker task and the CLI script."""
    engine = create_engine(settings.database_url)
    try:
        source = Tmdb5000CsvSource(settings.catalog_data_dir)
        return await import_catalog(create_session_factory(engine), source)
    finally:
        await engine.dispose()
