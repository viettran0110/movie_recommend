"""Bulk upserts for the catalog importer (PostgreSQL INSERT ... ON CONFLICT).

Every upsert is idempotent: conflicting rows are updated only when a source-provided
column actually differs, so a re-import of unchanged data writes nothing. Nothing here
deletes rows. Columns a source does not provide (poster_path, imdb_id, ...) are never
overwritten, so data from other jobs such as poster enrichment survives a re-import.
"""

from collections.abc import Iterable, Iterator, Mapping, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, ColumnElement, case, func, literal_column, or_, select
from sqlalchemy.dialects.postgresql import Insert, insert
from sqlalchemy.ext.asyncio import AsyncSession

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

Row = dict[str, Any]

# asyncpg allows at most 32,767 bind parameters per statement.
_MAX_PARAMS = 30_000

TITLE_SOURCE_COLUMNS = (
    "title",
    "original_title",
    "slug",
    "overview",
    "tagline",
    "original_language",
    "release_date",
    "status",
    "tmdb_popularity",
    "tmdb_vote_avg",
    "tmdb_vote_count",
)
MOVIE_DETAIL_SOURCE_COLUMNS = ("runtime", "budget", "revenue")
CREDIT_SOURCE_COLUMNS = ("title_id", "person_id", "role", "job", "character", "sort_order")


def _chunks(rows: Sequence[Row]) -> Iterator[Sequence[Row]]:
    if not rows:
        return
    size = max(1, _MAX_PARAMS // len(rows[0]))
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


def _changed(stmt: Insert, table: Any, columns: Iterable[str]) -> ColumnElement[bool]:
    return or_(*(getattr(table, c).is_distinct_from(stmt.excluded[c]) for c in columns))


def _update_set(stmt: Insert, columns: Iterable[str]) -> dict[str, Any]:
    values: dict[str, Any] = {c: stmt.excluded[c] for c in columns}
    values["updated_at"] = func.now()
    return values


async def _id_map(
    session: AsyncSession, model: type[Genre | Keyword | Person], tmdb_ids: Iterable[int]
) -> dict[int, int]:
    ids = list(tmdb_ids)
    if not ids:
        return {}
    result = await session.execute(select(model.tmdb_id, model.id).where(model.tmdb_id.in_(ids)))
    return {tmdb_id: row_id for tmdb_id, row_id in result}


async def upsert_genres(session: AsyncSession, rows: Sequence[Row]) -> dict[int, int]:
    """rows: tmdb_id, name, slug, media_types. Merges media_types. Returns tmdb_id -> id."""
    for chunk in _chunks(rows):
        stmt = insert(Genre)
        merged_types = case(
            (Genre.media_types.contains(stmt.excluded.media_types), Genre.media_types),
            else_=Genre.media_types.concat(stmt.excluded.media_types),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[Genre.tmdb_id],
            set_={**_update_set(stmt, ("name", "slug")), "media_types": merged_types},
            where=or_(
                _changed(stmt, Genre, ("name", "slug")),
                ~Genre.media_types.contains(stmt.excluded.media_types),
            ),
        )
        await session.execute(stmt, list(chunk))
    return await _id_map(session, Genre, (r["tmdb_id"] for r in rows))


async def _upsert_named(
    session: AsyncSession, model: type[Keyword | Person], rows: Sequence[Row]
) -> dict[int, int]:
    for chunk in _chunks(rows):
        stmt = insert(model)
        stmt = stmt.on_conflict_do_update(
            index_elements=[model.tmdb_id],
            set_=_update_set(stmt, ("name",)),
            where=_changed(stmt, model, ("name",)),
        )
        await session.execute(stmt, list(chunk))
    return await _id_map(session, model, (r["tmdb_id"] for r in rows))


async def upsert_keywords(session: AsyncSession, rows: Sequence[Row]) -> dict[int, int]:
    """rows: tmdb_id, name. Returns tmdb_id -> id."""
    return await _upsert_named(session, Keyword, rows)


async def upsert_people(session: AsyncSession, rows: Sequence[Row]) -> dict[int, int]:
    """rows: tmdb_id, name. Returns tmdb_id -> id."""
    return await _upsert_named(session, Person, rows)


async def upsert_titles(
    session: AsyncSession, rows: Sequence[Row], imported_at: datetime
) -> tuple[dict[tuple[MediaType, int], int], set[int], set[int]]:
    """rows: media_type, tmdb_id and TITLE_SOURCE_COLUMNS.

    Returns ((media_type, tmdb_id) -> id, inserted ids, updated ids). imported_at is set
    on inserted and changed rows only.
    """
    inserted: set[int] = set()
    updated: set[int] = set()
    for chunk in _chunks([{**r, "imported_at": imported_at} for r in rows]):
        stmt = insert(Title)
        upsert = stmt.on_conflict_do_update(
            index_elements=[Title.media_type, Title.tmdb_id],
            set_={
                **_update_set(stmt, TITLE_SOURCE_COLUMNS),
                "imported_at": stmt.excluded.imported_at,
            },
            where=_changed(stmt, Title, TITLE_SOURCE_COLUMNS),
        ).returning(Title.id, literal_column("xmax = 0", Boolean).label("inserted"))
        # xmax = 0 marks a freshly inserted row; an updated row carries a non-zero xmax.
        for title_id, was_inserted in await session.execute(upsert, list(chunk)):
            (inserted if was_inserted else updated).add(title_id)

    ids: dict[tuple[MediaType, int], int] = {}
    keys_by_type: dict[MediaType, list[int]] = {}
    for r in rows:
        keys_by_type.setdefault(r["media_type"], []).append(r["tmdb_id"])
    for media_type, tmdb_ids in keys_by_type.items():
        result = await session.execute(
            select(Title.tmdb_id, Title.id).where(
                Title.media_type == media_type, Title.tmdb_id.in_(tmdb_ids)
            )
        )
        ids.update({(media_type, tmdb_id): row_id for tmdb_id, row_id in result})
    return ids, inserted, updated


async def upsert_movie_details(session: AsyncSession, rows: Sequence[Row]) -> set[int]:
    """rows: title_id and MOVIE_DETAIL_SOURCE_COLUMNS. Returns title ids written."""
    changed: set[int] = set()
    for chunk in _chunks(rows):
        stmt = insert(MovieDetails)
        upsert_details = stmt.on_conflict_do_update(
            index_elements=[MovieDetails.title_id],
            set_=_update_set(stmt, MOVIE_DETAIL_SOURCE_COLUMNS),
            where=_changed(stmt, MovieDetails, MOVIE_DETAIL_SOURCE_COLUMNS),
        ).returning(MovieDetails.title_id)
        changed.update((await session.execute(upsert_details, list(chunk))).scalars())
    return changed


async def _link(
    session: AsyncSession, model: type[TitleGenre | TitleKeyword], rows: Sequence[Row]
) -> set[int]:
    changed: set[int] = set()
    for chunk in _chunks(rows):
        stmt = insert(model).on_conflict_do_nothing()
        changed.update(
            (await session.execute(stmt.returning(model.title_id), list(chunk))).scalars()
        )
    return changed


async def link_title_genres(session: AsyncSession, rows: Sequence[Row]) -> set[int]:
    """rows: title_id, genre_id. Adds missing links only. Returns title ids with new links."""
    return await _link(session, TitleGenre, rows)


async def link_title_keywords(session: AsyncSession, rows: Sequence[Row]) -> set[int]:
    """rows: title_id, keyword_id. Adds missing links only. Returns title ids with new links."""
    return await _link(session, TitleKeyword, rows)


async def upsert_credits(session: AsyncSession, rows: Sequence[Row]) -> set[int]:
    """rows: tmdb_credit_id and CREDIT_SOURCE_COLUMNS. Returns title ids written."""
    changed: set[int] = set()
    for chunk in _chunks(rows):
        stmt = insert(TitleCredit)
        upsert_credits = stmt.on_conflict_do_update(
            index_elements=[TitleCredit.tmdb_credit_id],
            set_=_update_set(stmt, CREDIT_SOURCE_COLUMNS),
            where=_changed(stmt, TitleCredit, CREDIT_SOURCE_COLUMNS),
        ).returning(TitleCredit.title_id)
        changed.update((await session.execute(upsert_credits, list(chunk))).scalars())
    return changed


def unique_by(rows: Iterable[Row], key: str) -> list[Row]:
    """Last row wins. ON CONFLICT cannot touch the same key twice in one statement."""
    by_key: Mapping[Any, Row] = {r[key]: r for r in rows}
    return list(by_key.values())
