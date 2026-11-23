"""Response schemas for the catalog read API (api-contracts.md "Catalog and explore").

Shapes are media-type agnostic (ADR-019): type-specific fields live in a nested object named
after the media type (`movie`), which is null for other types.
"""

from datetime import date

from pydantic import BaseModel

from app.modules.titles.models import MediaType, TitleStatus


class Page[T](BaseModel):
    items: list[T]
    page: int
    page_size: int
    total: int


class GenreRef(BaseModel):
    id: int
    name: str
    slug: str


class Genre(GenreRef):
    media_types: list[MediaType]


class MovieFields(BaseModel):
    runtime: int | None
    budget: int | None
    revenue: int | None


class TitleSummary(BaseModel):
    """A title in a list: enough for a card (poster or placeholder, name, year, rating)."""

    id: int
    media_type: MediaType
    slug: str
    title: str
    release_date: date | None
    poster_path: str | None
    tmdb_vote_avg: float | None
    tmdb_vote_count: int


class TitleDetail(TitleSummary):
    original_title: str
    overview: str | None
    tagline: str | None
    original_language: str | None
    backdrop_path: str | None
    status: TitleStatus | None
    tmdb_popularity: float | None
    score_avg: float | None
    score_count: int
    members_count: int
    genres: list[GenreRef]
    keywords: list[str]
    movie: MovieFields | None


class PersonRef(BaseModel):
    id: int
    name: str
    profile_path: str | None


class CastCredit(BaseModel):
    person: PersonRef
    character: str | None
    order: int | None


class CrewCredit(BaseModel):
    person: PersonRef
    job: str | None


class TitleCredits(BaseModel):
    title_id: int
    cast: list[CastCredit]
    crew: list[CrewCredit]
