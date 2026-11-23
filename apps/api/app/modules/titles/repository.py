"""Read queries over the catalog tables. Writes belong to app.modules.catalog."""

from collections.abc import Sequence

from sqlalchemy import ColumnElement, func, select
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


async def get_title(session: AsyncSession, title_id: int) -> Title | None:
    return await session.get(Title, title_id)


async def title_exists(session: AsyncSession, title_id: int) -> bool:
    stmt = select(Title.id).where(Title.id == title_id)
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def get_movie_details(session: AsyncSession, title_id: int) -> MovieDetails | None:
    return await session.get(MovieDetails, title_id)


async def list_title_genres(session: AsyncSession, title_id: int) -> Sequence[Genre]:
    stmt = (
        select(Genre)
        .join(TitleGenre, TitleGenre.genre_id == Genre.id)
        .where(TitleGenre.title_id == title_id)
        .order_by(Genre.name)
    )
    return (await session.execute(stmt)).scalars().all()


async def list_title_keywords(session: AsyncSession, title_id: int) -> Sequence[str]:
    stmt = (
        select(Keyword.name)
        .join(TitleKeyword, TitleKeyword.keyword_id == Keyword.id)
        .where(TitleKeyword.title_id == title_id)
        .order_by(Keyword.name)
    )
    return (await session.execute(stmt)).scalars().all()


async def list_title_credits(
    session: AsyncSession, title_id: int
) -> Sequence[tuple[TitleCredit, Person]]:
    """Cast by billing order, then crew by job and name; ids break ties deterministically."""
    stmt = (
        select(TitleCredit, Person)
        .join(Person, Person.id == TitleCredit.person_id)
        .where(TitleCredit.title_id == title_id)
        .order_by(
            TitleCredit.role,
            TitleCredit.sort_order.asc().nulls_last(),
            TitleCredit.job,
            Person.name,
            TitleCredit.id,
        )
    )
    return [(credit, person) for credit, person in (await session.execute(stmt)).all()]


async def list_genres(session: AsyncSession, media_type: MediaType | None) -> Sequence[Genre]:
    stmt = select(Genre).order_by(Genre.name)
    if media_type is not None:
        stmt = stmt.where(Genre.media_types.contains([media_type]))
    return (await session.execute(stmt)).scalars().all()


async def get_genre_by_slug(session: AsyncSession, slug: str) -> Genre | None:
    stmt = select(Genre).where(Genre.slug == slug)
    return (await session.execute(stmt)).scalar_one_or_none()


def _genre_titles_where(genre_id: int, media_type: MediaType | None) -> list[ColumnElement[bool]]:
    conditions = [TitleGenre.genre_id == genre_id]
    if media_type is not None:
        conditions.append(Title.media_type == media_type)
    return conditions


async def list_genre_titles(
    session: AsyncSession,
    genre_id: int,
    media_type: MediaType | None,
    *,
    offset: int,
    limit: int,
) -> tuple[Sequence[Title], int]:
    """Titles in a genre by TMDB popularity (most popular first), with the total count."""
    join = (TitleGenre, TitleGenre.title_id == Title.id)
    where = _genre_titles_where(genre_id, media_type)
    count_stmt = select(func.count(Title.id)).join(*join).where(*where)
    total = (await session.execute(count_stmt)).scalar_one()

    items_stmt = (
        select(Title)
        .join(*join)
        .where(*where)
        .order_by(Title.tmdb_popularity.desc().nulls_last(), Title.id)
        .offset(offset)
        .limit(limit)
    )
    items = (await session.execute(items_stmt)).scalars().all()
    return items, total
