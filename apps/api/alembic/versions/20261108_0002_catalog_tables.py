"""catalog tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-08

titles (media-type root, ADR-019), movie_details, genres, keywords, people, title_credits
and the link tables. Filled by the CSV catalog importer (ADR-023).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

media_type = postgresql.ENUM("movie", name="media_type", create_type=False)
title_status = postgresql.ENUM(
    "rumored",
    "planned",
    "in_production",
    "post_production",
    "released",
    "canceled",
    name="title_status",
    create_type=False,
)
credit_role = postgresql.ENUM("cast", "crew", name="credit_role", create_type=False)

ENUMS = (media_type, title_status, credit_role)


def _created_at() -> sa.Column[sa.DateTime]:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def _updated_at() -> sa.Column[sa.DateTime]:
    return sa.Column(
        "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def upgrade() -> None:
    bind = op.get_bind()
    for enum in ENUMS:
        enum.create(bind, checkfirst=False)

    op.create_table(
        "titles",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("media_type", media_type, nullable=False),
        sa.Column("tmdb_id", sa.Integer(), nullable=False),
        sa.Column("imdb_id", sa.String(16), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("original_title", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("overview", sa.Text(), nullable=True),
        sa.Column("tagline", sa.Text(), nullable=True),
        sa.Column("original_language", sa.String(8), nullable=True),
        sa.Column("poster_path", sa.Text(), nullable=True),
        sa.Column("backdrop_path", sa.Text(), nullable=True),
        sa.Column("release_date", sa.Date(), nullable=True),
        sa.Column("status", title_status, nullable=True),
        sa.Column("tmdb_popularity", sa.Double(), nullable=True),
        sa.Column("tmdb_vote_avg", sa.Numeric(3, 1), nullable=True),
        sa.Column("tmdb_vote_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("score_avg", sa.Numeric(4, 2), nullable=True),
        sa.Column("score_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("members_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id", name="pk_titles"),
        sa.UniqueConstraint("media_type", "tmdb_id", name="uq_titles_media_type"),
        sa.CheckConstraint("tmdb_vote_avg BETWEEN 0 AND 10", name="ck_titles_tmdb_vote_avg_range"),
        sa.CheckConstraint("score_avg BETWEEN 1 AND 10", name="ck_titles_score_avg_range"),
    )
    op.create_index("ix_titles_media_type_release_date", "titles", ["media_type", "release_date"])
    op.create_index(
        "ix_titles_title_trgm",
        "titles",
        ["title"],
        postgresql_using="gin",
        postgresql_ops={"title": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_titles_original_title_trgm",
        "titles",
        ["original_title"],
        postgresql_using="gin",
        postgresql_ops={"original_title": "gin_trgm_ops"},
    )

    op.create_table(
        "movie_details",
        sa.Column("title_id", sa.BigInteger(), nullable=False),
        sa.Column("runtime", sa.SmallInteger(), nullable=True),
        sa.Column("budget", sa.BigInteger(), nullable=True),
        sa.Column("revenue", sa.BigInteger(), nullable=True),
        sa.Column("collection_tmdb_id", sa.Integer(), nullable=True),
        _updated_at(),
        sa.PrimaryKeyConstraint("title_id", name="pk_movie_details"),
        sa.ForeignKeyConstraint(
            ["title_id"], ["titles.id"], name="fk_movie_details_title_id_titles"
        ),
    )

    op.create_table(
        "genres",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("tmdb_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column(
            "media_types",
            postgresql.ARRAY(media_type),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id", name="pk_genres"),
        sa.UniqueConstraint("tmdb_id", name="uq_genres_tmdb_id"),
        sa.UniqueConstraint("slug", name="uq_genres_slug"),
    )

    op.create_table(
        "title_genres",
        sa.Column("title_id", sa.BigInteger(), nullable=False),
        sa.Column("genre_id", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("title_id", "genre_id", name="pk_title_genres"),
        sa.ForeignKeyConstraint(
            ["title_id"], ["titles.id"], name="fk_title_genres_title_id_titles"
        ),
        sa.ForeignKeyConstraint(
            ["genre_id"], ["genres.id"], name="fk_title_genres_genre_id_genres"
        ),
    )
    op.create_index("ix_title_genres_genre_id", "title_genres", ["genre_id"])

    op.create_table(
        "keywords",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("tmdb_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id", name="pk_keywords"),
        sa.UniqueConstraint("tmdb_id", name="uq_keywords_tmdb_id"),
    )

    op.create_table(
        "title_keywords",
        sa.Column("title_id", sa.BigInteger(), nullable=False),
        sa.Column("keyword_id", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("title_id", "keyword_id", name="pk_title_keywords"),
        sa.ForeignKeyConstraint(
            ["title_id"], ["titles.id"], name="fk_title_keywords_title_id_titles"
        ),
        sa.ForeignKeyConstraint(
            ["keyword_id"], ["keywords.id"], name="fk_title_keywords_keyword_id_keywords"
        ),
    )
    op.create_index("ix_title_keywords_keyword_id", "title_keywords", ["keyword_id"])

    op.create_table(
        "people",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("tmdb_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("profile_path", sa.Text(), nullable=True),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id", name="pk_people"),
        sa.UniqueConstraint("tmdb_id", name="uq_people_tmdb_id"),
    )

    op.create_table(
        "title_credits",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("tmdb_credit_id", sa.String(32), nullable=False),
        sa.Column("title_id", sa.BigInteger(), nullable=False),
        sa.Column("person_id", sa.BigInteger(), nullable=False),
        sa.Column("role", credit_role, nullable=False),
        sa.Column("job", sa.Text(), nullable=True),
        sa.Column("character", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.SmallInteger(), nullable=True),
        _created_at(),
        _updated_at(),
        sa.PrimaryKeyConstraint("id", name="pk_title_credits"),
        sa.UniqueConstraint("tmdb_credit_id", name="uq_title_credits_tmdb_credit_id"),
        sa.ForeignKeyConstraint(
            ["title_id"], ["titles.id"], name="fk_title_credits_title_id_titles"
        ),
        sa.ForeignKeyConstraint(
            ["person_id"], ["people.id"], name="fk_title_credits_person_id_people"
        ),
    )
    op.create_index("ix_title_credits_person_id", "title_credits", ["person_id"])
    op.create_index(
        "ix_title_credits_title_id_role_sort_order",
        "title_credits",
        ["title_id", "role", "sort_order"],
    )


def downgrade() -> None:
    # Drops only the tables this revision created (empty before any import).
    for table in (
        "title_credits",
        "people",
        "title_keywords",
        "keywords",
        "title_genres",
        "genres",
        "movie_details",
        "titles",
    ):
        op.drop_table(table)
    bind = op.get_bind()
    for enum in reversed(ENUMS):
        enum.drop(bind, checkfirst=False)
