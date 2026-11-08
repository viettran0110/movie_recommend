"""Catalog tables (data-model.md). `titles` is the media-type-agnostic root (ADR-019).

Written by the catalog importer (app.modules.catalog); read by the titles API (Phase 1).
"""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Double,
    Enum,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class MediaType(StrEnum):
    # Only movies at launch. Adding `tv` is an additive enum migration (ADR-019).
    MOVIE = "movie"


class TitleStatus(StrEnum):
    # TMDB movie statuses. TV statuses (returning_series, ended, ...) are added with TV.
    RUMORED = "rumored"
    PLANNED = "planned"
    IN_PRODUCTION = "in_production"
    POST_PRODUCTION = "post_production"
    RELEASED = "released"
    CANCELED = "canceled"


class CreditRole(StrEnum):
    CAST = "cast"
    CREW = "crew"


def _pg_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    # Store the lowercase values, not the Python member names.
    return Enum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e])


media_type_enum = _pg_enum(MediaType, "media_type")
title_status_enum = _pg_enum(TitleStatus, "title_status")
credit_role_enum = _pg_enum(CreditRole, "credit_role")


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


def _updated_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Title(Base):
    __tablename__ = "titles"
    __table_args__ = (
        UniqueConstraint("media_type", "tmdb_id"),
        CheckConstraint("tmdb_vote_avg BETWEEN 0 AND 10", name="tmdb_vote_avg_range"),
        CheckConstraint("score_avg BETWEEN 1 AND 10", name="score_avg_range"),
        Index("ix_titles_media_type_release_date", "media_type", "release_date"),
        # Fallback fuzzy match only; primary search is Meilisearch (ADR-018).
        Index(
            "ix_titles_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
        Index(
            "ix_titles_original_title_trgm",
            "original_title",
            postgresql_using="gin",
            postgresql_ops={"original_title": "gin_trgm_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    media_type: Mapped[MediaType] = mapped_column(media_type_enum)
    tmdb_id: Mapped[int] = mapped_column(Integer)
    imdb_id: Mapped[str | None] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(Text)
    original_title: Mapped[str] = mapped_column(Text)
    # Not unique: URLs are /movie/{id}-{slug}; the id is authoritative.
    slug: Mapped[str] = mapped_column(Text)
    overview: Mapped[str | None] = mapped_column(Text)
    tagline: Mapped[str | None] = mapped_column(Text)
    original_language: Mapped[str | None] = mapped_column(String(8))
    poster_path: Mapped[str | None] = mapped_column(Text)
    backdrop_path: Mapped[str | None] = mapped_column(Text)
    release_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[TitleStatus | None] = mapped_column(title_status_enum)
    tmdb_popularity: Mapped[float | None] = mapped_column(Double)
    tmdb_vote_avg: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    tmdb_vote_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    # Denormalized from user_title_entries by a worker job (Phase 2); never per request.
    score_avg: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    score_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    members_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class MovieDetails(Base):
    __tablename__ = "movie_details"

    title_id: Mapped[int] = mapped_column(ForeignKey("titles.id"), primary_key=True)
    runtime: Mapped[int | None] = mapped_column(SmallInteger)
    budget: Mapped[int | None] = mapped_column(BigInteger)
    revenue: Mapped[int | None] = mapped_column(BigInteger)
    collection_tmdb_id: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = _updated_at()


class Genre(Base):
    __tablename__ = "genres"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    tmdb_id: Mapped[int] = mapped_column(Integer, unique=True)
    name: Mapped[str] = mapped_column(Text)
    slug: Mapped[str] = mapped_column(Text, unique=True)
    media_types: Mapped[list[MediaType]] = mapped_column(
        ARRAY(media_type_enum), server_default=text("'{}'")
    )
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class TitleGenre(Base):
    __tablename__ = "title_genres"

    title_id: Mapped[int] = mapped_column(ForeignKey("titles.id"), primary_key=True)
    genre_id: Mapped[int] = mapped_column(ForeignKey("genres.id"), primary_key=True, index=True)


class Keyword(Base):
    __tablename__ = "keywords"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    tmdb_id: Mapped[int] = mapped_column(Integer, unique=True)
    name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class TitleKeyword(Base):
    __tablename__ = "title_keywords"

    title_id: Mapped[int] = mapped_column(ForeignKey("titles.id"), primary_key=True)
    keyword_id: Mapped[int] = mapped_column(ForeignKey("keywords.id"), primary_key=True, index=True)


class Person(Base):
    __tablename__ = "people"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    tmdb_id: Mapped[int] = mapped_column(Integer, unique=True)
    name: Mapped[str] = mapped_column(Text)
    profile_path: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class TitleCredit(Base):
    __tablename__ = "title_credits"
    __table_args__ = (
        Index("ix_title_credits_title_id_role_sort_order", "title_id", "role", "sort_order"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    # TMDB credit ids are globally unique strings; the idempotent upsert key.
    tmdb_credit_id: Mapped[str] = mapped_column(String(32), unique=True)
    title_id: Mapped[int] = mapped_column(ForeignKey("titles.id"))
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"), index=True)
    role: Mapped[CreditRole] = mapped_column(credit_role_enum)
    job: Mapped[str | None] = mapped_column(Text)  # crew only, e.g. "Director"
    character: Mapped[str | None] = mapped_column(Text)  # cast only
    sort_order: Mapped[int | None] = mapped_column(SmallInteger)  # cast billing order
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()
