"""Source-agnostic catalog records. Every CatalogSource maps its raw rows into these."""

from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.modules.titles.models import CreditRole, MediaType, TitleStatus

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
TmdbId = Annotated[int, Field(gt=0, le=2_147_483_647)]
SmallInt = Annotated[int, Field(ge=0, le=32_767)]


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class GenreRecord(_Record):
    tmdb_id: TmdbId
    name: NonEmptyStr


class KeywordRecord(_Record):
    tmdb_id: TmdbId
    name: NonEmptyStr


class CreditRecord(_Record):
    tmdb_credit_id: Annotated[str, StringConstraints(min_length=1, max_length=32)]
    person_tmdb_id: TmdbId
    person_name: NonEmptyStr
    role: CreditRole
    job: str | None = None
    character: str | None = None
    sort_order: SmallInt | None = None


class MovieDetailsRecord(_Record):
    # None means unknown; sources map their "0 = unknown" values to None.
    runtime: Annotated[int, Field(gt=0, le=32_767)] | None = None
    budget: Annotated[int, Field(gt=0)] | None = None
    revenue: Annotated[int, Field(gt=0)] | None = None


class TitleRecord(_Record):
    media_type: MediaType
    tmdb_id: TmdbId
    title: NonEmptyStr
    original_title: NonEmptyStr
    overview: str | None = None
    tagline: str | None = None
    original_language: Annotated[str, StringConstraints(max_length=8)] | None = None
    release_date: date | None = None
    status: TitleStatus | None = None
    tmdb_popularity: Annotated[float, Field(ge=0)] | None = None
    # Matches numeric(3,1), so a re-import compares equal and is not seen as a change.
    tmdb_vote_avg: Annotated[Decimal, Field(ge=0, le=10, max_digits=3, decimal_places=1)] | None = (
        None
    )
    tmdb_vote_count: Annotated[int, Field(ge=0)] = 0


class CatalogRecord(_Record):
    title: TitleRecord
    # Type-specific extension row; its type must match title.media_type (see service).
    details: MovieDetailsRecord | None = None
    genres: tuple[GenreRecord, ...] = ()
    keywords: tuple[KeywordRecord, ...] = ()
    credits: tuple[CreditRecord, ...] = ()


class InvalidRecord(_Record):
    """A source row that failed validation. Counted and logged by id, never fatal."""

    source_id: str
    error: str


class ImportReport(BaseModel):
    source: str
    titles_inserted: int = 0
    # Existing titles where the title row or any of its details, genres, keywords or
    # credits changed.
    titles_updated: int = 0
    titles_unchanged: int = 0
    invalid: int = 0
    # Database ids of inserted or updated titles: the input for reindex jobs.
    changed_title_ids: list[int] = Field(default_factory=list)
