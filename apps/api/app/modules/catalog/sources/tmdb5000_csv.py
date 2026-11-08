"""The TMDB 5000 Kaggle export: tmdb_5000_movies.csv + tmdb_5000_credits.csv (ADR-023).

The files are joined on movies.id = credits.movie_id. Nested columns hold JSON arrays and
are parsed with json.loads. Columns outside the data model (production_companies,
production_countries, spoken_languages, homepage) are ignored.
"""

import csv
import json
import logging
from collections.abc import Iterable, Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from app.modules.catalog.schemas import (
    CatalogRecord,
    CreditRecord,
    GenreRecord,
    InvalidRecord,
    KeywordRecord,
    MovieDetailsRecord,
    TitleRecord,
)
from app.modules.titles.models import CreditRole, MediaType, TitleStatus

logger = logging.getLogger(__name__)

MOVIES_FILE = "tmdb_5000_movies.csv"
CREDITS_FILE = "tmdb_5000_credits.csv"
MOVIE_COLUMNS = frozenset(
    {
        "id",
        "title",
        "original_title",
        "overview",
        "tagline",
        "original_language",
        "release_date",
        "status",
        "popularity",
        "vote_average",
        "vote_count",
        "runtime",
        "budget",
        "revenue",
        "genres",
        "keywords",
    }
)
CREDIT_COLUMNS = frozenset({"movie_id", "cast", "crew"})

# All cast is kept; crew only for these jobs (the full crew is ~130k rows of little use).
KEPT_CREW_JOBS = frozenset(
    {
        "Director",
        "Writer",
        "Screenplay",
        "Producer",
        "Original Music Composer",
        "Director of Photography",
    }
)

# Credits cells hold whole cast lists and exceed csv's 128 KiB default field limit.
_FIELD_SIZE_LIMIT = 16 * 1024 * 1024
_MAX_ERROR_LENGTH = 500


def _parse_json_list(value: object) -> object:
    if isinstance(value, str):
        return json.loads(value) if value.strip() else []
    return value


def _blank_to_none(value: object) -> object:
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _zero_to_none(value: object) -> object:
    # "0", "0.0" and "" mean unknown in this export.
    value = _blank_to_none(value)
    if isinstance(value, str) and float(value) == 0:
        return None
    return value


class _IdName(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: int
    name: str


class _CastMember(BaseModel):
    model_config = ConfigDict(extra="ignore")
    credit_id: str
    id: int
    name: str
    character: str | None = None
    order: int | None = None


class _CrewMember(BaseModel):
    model_config = ConfigDict(extra="ignore")
    credit_id: str
    id: int
    name: str
    job: str


class _MovieRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    title: str
    original_title: str | None = None
    overview: str | None = None
    tagline: str | None = None
    original_language: str | None = None
    release_date: date | None = None
    status: TitleStatus | None = None
    popularity: float | None = None
    vote_average: Decimal | None = None
    vote_count: int = 0
    runtime: int | None = None
    budget: int | None = None
    revenue: int | None = None
    genres: list[_IdName]
    keywords: list[_IdName]

    @field_validator("genres", "keywords", mode="before")
    @classmethod
    def parse_json_lists(cls, value: object) -> object:
        return _parse_json_list(value)

    @field_validator(
        "original_title",
        "overview",
        "tagline",
        "original_language",
        "release_date",
        "popularity",
        "vote_average",
        mode="before",
    )
    @classmethod
    def blank_to_none(cls, value: object) -> object:
        return _blank_to_none(value)

    @field_validator("budget", "revenue", mode="before")
    @classmethod
    def zero_to_none(cls, value: object) -> object:
        return _zero_to_none(value)

    @field_validator("runtime", mode="before")
    @classmethod
    def parse_runtime(cls, value: object) -> object:
        # Runtime is written as "162" or "162.0"; 0 means unknown.
        value = _zero_to_none(value)
        return round(float(value)) if isinstance(value, str) else value

    @field_validator("status", mode="before")
    @classmethod
    def parse_status(cls, value: object) -> object:
        # "Post Production" -> "post_production"
        value = _blank_to_none(value)
        return value.strip().lower().replace(" ", "_") if isinstance(value, str) else value


class _CreditsRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    movie_id: int
    cast: list[_CastMember]
    crew: list[_CrewMember]

    @field_validator("cast", "crew", mode="before")
    @classmethod
    def parse_json_lists(cls, value: object) -> object:
        return _parse_json_list(value)


def _describe(error: Exception) -> str:
    if isinstance(error, ValidationError):
        # Locations and messages only: never echo cell contents into logs.
        text = "; ".join(
            f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
            for item in error.errors(include_input=False, include_url=False)
        )
    else:
        text = f"{type(error).__name__}: {error}"
    return text[:_MAX_ERROR_LENGTH]


def _to_record(movie: _MovieRow, credits: _CreditsRow | None) -> CatalogRecord:
    title = TitleRecord(
        media_type=MediaType.MOVIE,
        tmdb_id=movie.id,
        title=movie.title,
        original_title=movie.original_title or movie.title,
        overview=movie.overview,
        tagline=movie.tagline,
        original_language=movie.original_language,
        release_date=movie.release_date,
        status=movie.status,
        tmdb_popularity=movie.popularity,
        tmdb_vote_avg=movie.vote_average,
        tmdb_vote_count=movie.vote_count,
    )
    details = MovieDetailsRecord(runtime=movie.runtime, budget=movie.budget, revenue=movie.revenue)
    credit_data: list[dict[str, object]] = []
    if credits is not None:
        credit_data.extend(
            {
                "tmdb_credit_id": member.credit_id,
                "person_tmdb_id": member.id,
                "person_name": member.name,
                "role": CreditRole.CAST,
                "character": member.character or None,
                "sort_order": member.order,
            }
            for member in credits.cast
        )
        credit_data.extend(
            {
                "tmdb_credit_id": member.credit_id,
                "person_tmdb_id": member.id,
                "person_name": member.name,
                "role": CreditRole.CREW,
                "job": member.job,
            }
            for member in credits.crew
            if member.job in KEPT_CREW_JOBS
        )
    return CatalogRecord(
        title=title,
        details=details,
        genres=_keep_valid(
            movie.id, GenreRecord, ({"tmdb_id": g.id, "name": g.name} for g in movie.genres)
        ),
        keywords=_keep_valid(
            movie.id, KeywordRecord, ({"tmdb_id": k.id, "name": k.name} for k in movie.keywords)
        ),
        credits=_keep_valid(movie.id, CreditRecord, credit_data),
    )


def _keep_valid[M: BaseModel](
    title_tmdb_id: int, model: type[M], items: Iterable[dict[str, object]]
) -> tuple[M, ...]:
    # One bad nested item (e.g. a keyword whose name is only a non-breaking space) drops
    # that item, not the whole title.
    kept: list[M] = []
    for data in items:
        try:
            kept.append(model.model_validate(data))
        except ValidationError as error:
            logger.warning(
                "skipping invalid %s of title %s: %s",
                model.__name__,
                title_tmdb_id,
                _describe(error),
            )
    return tuple(kept)


class Tmdb5000CsvSource:
    def __init__(self, data_dir: Path) -> None:
        self._movies_path = data_dir / MOVIES_FILE
        self._credits_path = data_dir / CREDITS_FILE

    @property
    def name(self) -> str:
        return "tmdb5000_csv"

    def read(self) -> Iterator[CatalogRecord | InvalidRecord]:
        csv.field_size_limit(_FIELD_SIZE_LIMIT)
        credits = self._read_credits()
        seen: set[str] = set()
        for line, row in _read_rows(self._movies_path, MOVIE_COLUMNS):
            source_id = (row.get("id") or "").strip() or f"{MOVIES_FILE}:{line}"
            if source_id in seen:
                yield InvalidRecord(source_id=source_id, error="duplicate id")
                continue
            seen.add(source_id)
            try:
                movie = _MovieRow.model_validate(row)
                raw_credits = credits.get(source_id)
                if raw_credits is None:
                    logger.warning("no credits row for source id %s", source_id)
                    movie_credits = None
                else:
                    movie_credits = _CreditsRow.model_validate(raw_credits)
                yield _to_record(movie, movie_credits)
            except (ValidationError, ValueError) as error:
                yield InvalidRecord(source_id=source_id, error=_describe(error))

    def _read_credits(self) -> dict[str, dict[str, Any]]:
        # Raw rows keyed by movie_id; parsed lazily so one bad row only fails its title.
        return {
            (row.get("movie_id") or "").strip(): row
            for _, row in _read_rows(self._credits_path, CREDIT_COLUMNS)
        }


def _read_rows(path: Path, required: frozenset[str]) -> Iterator[tuple[int, dict[str, Any]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path.name} is missing columns: {sorted(missing)}")
        for row in reader:
            yield reader.line_num, row
