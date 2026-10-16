# Data Model

Status: **Planned draft.** No database exists yet. Treat column lists as the starting point for the first Alembic migrations. Refine them in the same change that implements them, and update this file to match.

## Conventions

- Primary keys: `bigint` identity for catalog tables. `uuid` for `users` (not enumerable in URLs).
- Timestamps: `timestamptz`, UTC. Every mutable table has `created_at` and `updated_at`.
- Enums: Postgres enums, managed through Alembic.
- Foreign keys: always declared. `ON DELETE CASCADE` only for rows owned by a user (entries, reviews, tokens).
- Soft delete is used only where moderation needs it (reviews).

## Catalog

| Table | Key columns |
|---|---|
| `movies` | id, tmdb_id (unique), imdb_id, title, original_title, slug, overview, release_date, runtime, poster_path, backdrop_path, original_language, tmdb_popularity, tmdb_vote_avg, tmdb_vote_count, score_avg, score_count, members_count, updated_at |
| `genres` / `movie_genres` | id, tmdb_id, name, slug / (movie_id, genre_id) |
| `keywords` / `movie_keywords` | id, tmdb_id, name / (movie_id, keyword_id) |
| `people` | id, tmdb_id, name, profile_path |
| `movie_credits` | movie_id, person_id, role (`cast`/`crew`), job (e.g. Director), character, order |

- `score_avg`, `score_count` and `members_count` are denormalized from `user_movie_entries`. A worker job recomputes them; never compute them per request.
- `members_count` means the number of users with the movie in their list, in any status.

## Users and auth

| Table | Key columns |
|---|---|
| `users` | id (uuid), email (unique, citext), username (unique, citext), password_hash (nullable for OAuth-only), display_name, avatar_url, email_verified_at, is_admin, created_at |
| `oauth_accounts` | id, user_id, provider, provider_account_id (unique per provider) |
| `refresh_tokens` | id, user_id, family_id, token_hash (unique), expires_at, revoked_at, replaced_by_id, created_at, user_agent, ip_hash |

Token semantics are defined in [security.md](security.md).

## Tracking ("archive")

`user_movie_entries`: PK (user_id, movie_id).

| Column | Type / rule |
|---|---|
| status | enum `watching`, `completed`, `on_hold`, `dropped`, `plan_to_watch` |
| score | smallint 1–10, nullable |
| rewatch_count | smallint ≥ 0, default 0 |
| started_at, finished_at | date, nullable; `finished_at >= started_at` |
| notes | text, max 2000 chars |
| is_private | bool, default false |
| created_at, updated_at | timestamptz |

Other user content:

| Table | Key columns |
|---|---|
| `favorites` | (user_id, movie_id), position |
| `reviews` | id, user_id, movie_id, body, score_snapshot, is_spoiler, deleted_at; unique (user_id, movie_id) |
| `review_votes` | (review_id, user_id), helpful bool |
| `custom_lists` / `custom_list_items` | id, user_id, title, is_public / (list_id, movie_id, position, note) |
| `user_rec_submissions` | id, user_id, source_movie_id, target_movie_id, reason; check source ≠ target; unique (user_id, source, target) |
| `user_rec_agreements` | (submission_id, user_id) |
| `user_events` | id, user_id (nullable for anonymous), session_id, movie_id, type (`view`, `click_rec`, `add_to_list`, `rate`, `search_click`), context jsonb, created_at |

`user_events` is append-only and will grow quickly. Plan monthly partitioning or retention before production.

## Recommender output

These tables are written only by worker jobs; see [recommendation.md](recommendation.md).

| Table | Key columns |
|---|---|
| `movie_embeddings` | movie_id, model_version, embedding `vector(384)` |
| `item_similarities` | movie_id, similar_movie_id, score, source (`content`, `item_cf`), model_version |
| `user_recommendations` | user_id, movie_id, score, reason jsonb, source, model_version, generated_at |
| `movie_stats_daily` | movie_id, date, views, list_adds, ratings — input for trending |

## Indexes

- `pg_trgm` GIN index on `movies.title` and `movies.original_title`, for fuzzy fallback search.
- HNSW index on `movie_embeddings.embedding` (cosine ops).
- `user_movie_entries (user_id, status, updated_at DESC)` for profile lists.
- `user_movie_entries (movie_id)` for stats.
- `user_events (user_id, created_at)` and `(movie_id, created_at)`.

## Migration rules

- Every model change gets an Alembic revision, in the same commit as the model change.
- Revisions must be reversible (`downgrade` implemented) unless the commit body explains why not.
- Dropping or renaming columns or tables, or rewriting user data: write the migration as expand → backfill → contract, and **get explicit approval before running anything destructive** against a shared or production database.
- Never edit a migration that has already been applied to a shared environment. Add a new one instead.
