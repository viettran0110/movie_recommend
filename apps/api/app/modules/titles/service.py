"""Catalog read rules: 404s, media-type specific fields, and ORM → schema mapping.

Redis caching of `title:{id}` (api-contracts.md "Caching") is planned and not done yet.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.modules.titles import repository
from app.modules.titles.models import CreditRole, MediaType, Title
from app.modules.titles.schemas import (
    CastCredit,
    CrewCredit,
    Genre,
    GenreRef,
    MovieFields,
    Page,
    PersonRef,
    TitleCredits,
    TitleDetail,
    TitleSummary,
)


def _title_not_found(title_id: int) -> NotFoundError:
    return NotFoundError("Title not found", {"title_id": title_id})


def _summary_fields(title: Title) -> dict[str, object]:
    return {
        "id": title.id,
        "media_type": title.media_type,
        "slug": title.slug,
        "title": title.title,
        "release_date": title.release_date,
        "poster_path": title.poster_path,
        "tmdb_vote_avg": title.tmdb_vote_avg,
        "tmdb_vote_count": title.tmdb_vote_count,
    }


def to_summary(title: Title) -> TitleSummary:
    return TitleSummary.model_validate(_summary_fields(title))


async def get_title(session: AsyncSession, title_id: int) -> TitleDetail:
    title = await repository.get_title(session, title_id)
    if title is None:
        raise _title_not_found(title_id)

    movie: MovieFields | None = None
    if title.media_type == MediaType.MOVIE:
        details = await repository.get_movie_details(session, title_id)
        movie = MovieFields(
            runtime=details.runtime if details else None,
            budget=details.budget if details else None,
            revenue=details.revenue if details else None,
        )

    genres = await repository.list_title_genres(session, title_id)
    keywords = await repository.list_title_keywords(session, title_id)
    return TitleDetail.model_validate(
        {
            **_summary_fields(title),
            "original_title": title.original_title,
            "overview": title.overview,
            "tagline": title.tagline,
            "original_language": title.original_language,
            "backdrop_path": title.backdrop_path,
            "status": title.status,
            "tmdb_popularity": title.tmdb_popularity,
            "score_avg": title.score_avg,
            "score_count": title.score_count,
            "members_count": title.members_count,
            "genres": [GenreRef(id=g.id, name=g.name, slug=g.slug) for g in genres],
            "keywords": list(keywords),
            "movie": movie,
        }
    )


async def get_title_credits(session: AsyncSession, title_id: int) -> TitleCredits:
    if not await repository.title_exists(session, title_id):
        raise _title_not_found(title_id)

    cast: list[CastCredit] = []
    crew: list[CrewCredit] = []
    for credit, person in await repository.list_title_credits(session, title_id):
        ref = PersonRef(id=person.id, name=person.name, profile_path=person.profile_path)
        if credit.role == CreditRole.CAST:
            cast.append(CastCredit(person=ref, character=credit.character, order=credit.sort_order))
        else:
            crew.append(CrewCredit(person=ref, job=credit.job))
    return TitleCredits(title_id=title_id, cast=cast, crew=crew)


async def list_genres(session: AsyncSession, media_type: MediaType | None) -> list[Genre]:
    genres = await repository.list_genres(session, media_type)
    return [
        Genre(id=g.id, name=g.name, slug=g.slug, media_types=list(g.media_types)) for g in genres
    ]


async def list_genre_titles(
    session: AsyncSession,
    slug: str,
    media_type: MediaType | None,
    *,
    page: int,
    page_size: int,
) -> Page[TitleSummary]:
    genre = await repository.get_genre_by_slug(session, slug)
    if genre is None:
        raise NotFoundError("Genre not found", {"slug": slug})

    titles, total = await repository.list_genre_titles(
        session, genre.id, media_type, offset=(page - 1) * page_size, limit=page_size
    )
    return Page[TitleSummary](
        items=[to_summary(t) for t in titles], page=page, page_size=page_size, total=total
    )
