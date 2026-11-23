# API Contracts

Status: **Planned draft**, except the endpoints marked **current** (health, title detail and credits, genres) and the error envelope. FastAPI's generated OpenAPI schema becomes the source of truth once implemented. Keep this file as the human summary and update it in the same change.

## Conventions

- Base path `/api/v1`, JSON only, `snake_case` fields.
- Health check (current): `GET /api/v1/health` returns `{"status":"ok","checks":{"database":true,"redis":true,"meilisearch":true}}`. If any check fails or exceeds 2 s, it returns 503 with `"status":"degraded"` and the same `checks` shape. Error details are never returned.
- Docs: Swagger UI at `/api/v1/docs`, schema at `/api/v1/openapi.json`. The committed copy is `apps/api/openapi.json`.
- **Media types**: catalog resources are `titles`. Each title response includes `media_type` (`movie` at launch). List endpoints accept `?media_type=`, which defaults to all enabled types. Type-specific fields sit in a nested object (`movie: {runtime, ...}`). See [data-model.md](data-model.md) (ADR-019).
- Pagination: `?page=1&page_size=20` (max 100) returns `{"items": [...], "page", "page_size", "total"}`. Use cursor pagination (`?cursor=`) for event-style feeds.
- Errors (current, `app/core/errors.py`): `{"error": {"code": "string_slug", "message": "human readable", "details": {...}}}` with the matching HTTP status, also for unknown routes (`not_found`) and wrong methods (`method_not_allowed`). Services raise `AppError` subclasses (`NotFoundError` → 404). Validation errors return 422 with code `validation_error` and `details.errors` = `[{loc, msg, type}]`; the submitted input is never echoed.
- Auth: the access token comes from an httpOnly cookie ([security.md](security.md)). Mutating requests that use cookie auth must send the CSRF header.
- Ownership: every `/me/*` route acts only on the authenticated user. Never accept a `user_id` from the client for writes.
- Timestamps are ISO 8601 UTC. User-facing text is English only in v1 (ADR-020).

Auth column: **—** public, **U** authenticated user, **A** admin. **RL** means rate limited (limits in [security.md](security.md)).

## Auth

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/auth/register` | — RL | email, username, password |
| POST | `/auth/login` | — RL | Sets access, refresh, and CSRF cookies |
| POST | `/auth/refresh` | refresh cookie RL | Rotates the refresh token |
| POST | `/auth/logout` | U | Revokes the current refresh token family, clears cookies |
| POST | `/auth/logout-all` | U | Revokes all of the user's refresh tokens |
| GET | `/auth/oauth/google`, `/auth/oauth/google/callback` | — RL | Authlib, state + PKCE |
| POST | `/auth/password/forgot`, `/auth/password/reset` | — RL | Single-use, short-lived token |

## Catalog and explore

| Method | Path | Auth | Status |
|---|---|---|---|
| GET | `/titles/{id}` | — | current |
| GET | `/titles/{id}/credits` | — | current |
| GET | `/titles/{id}/similar` | — | |
| GET | `/titles/{id}/reviews` | — | |
| GET | `/titles/{id}/user-recs` | — | |
| GET | `/explore/top?media_type=&sort=score\|popularity\|members` | — | |
| GET | `/explore/trending?media_type=&window=day\|week` | — | |
| GET | `/explore/upcoming?media_type=` | — | |
| GET | `/genres?media_type=`, `/genres/{slug}/titles?media_type=&page=&page_size=` | — | current |

Current shapes (the OpenAPI schema is authoritative):

- `GET /titles/{id}` → `TitleDetail`: id, media_type, slug, title, original_title, overview, tagline, original_language, release_date, status, poster_path, backdrop_path, tmdb_vote_avg, tmdb_vote_count, tmdb_popularity, score_avg, score_count, members_count, `genres` [{id, name, slug}], `keywords` [names], and `movie` {runtime, budget, revenue} (null for other media types). Unknown values are null. `id` must be 1..2^63−1 (else 422); a missing title is 404 `not_found`.
- `GET /titles/{id}/credits` → {title_id, `cast` [{person {id, name, profile_path}, character, order}] by billing order, `crew` [{person, job}] by job then name}. Crew holds only the imported jobs ([data-model.md](data-model.md)).
- `GET /genres` → [{id, name, slug, media_types}] by name; `?media_type=` keeps genres used by that type.
- `GET /genres/{slug}/titles` → `Page` of `TitleSummary` {id, media_type, slug, title, release_date, poster_path, tmdb_vote_avg, tmdb_vote_count}, most TMDB-popular first, ties by id. `page` 1..10000, `page_size` 1..100 (default 20). Unknown slug is 404.
- The `title:{id}` Redis cache below is not implemented yet; these endpoints read Postgres directly.

## Search (core feature, Meilisearch — ADR-018)

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/search?q=&media_type=&genres=&year_from=&year_to=&min_score=&sort=&page=` | — RL | Full results with facet counts (`facets` object) |
| GET | `/search/suggest?q=&limit=` | — RL | Autocomplete: max 10 lightweight hits (id, media_type, title, year, poster_path — null until the optional poster job fills it, ADR-025); target p95 < 100 ms |

- Typo tolerance, prefix search, and ranking rules are configured in the Meilisearch index settings and kept in code (`app/integrations/meili_client.py`, planned). They are applied by a settings-sync job, never configured by hand.
- `sort` and filter fields are validated against an allow-list before they reach Meilisearch.

## User data

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/me` | U | |
| PATCH | `/me` | U | Profile fields only |
| GET | `/users/{username}` | — | Public profile |
| GET | `/users/{username}/list?status=&media_type=` | — | Excludes `is_private` entries unless the requester is the owner |
| PUT | `/me/list/{title_id}` | U | Upsert status, score, dates, notes (progress for TV later) |
| DELETE | `/me/list/{title_id}` | U | |
| GET | `/me/stats` | U | Counts by status, mean score, genre distribution |
| PUT/DELETE | `/me/favorites/{title_id}` | U | |
| POST | `/titles/{id}/reviews` | U RL | One per user per title |
| PATCH/DELETE | `/reviews/{id}` | owner or A | |
| PUT | `/reviews/{id}/vote` | U | |
| POST | `/titles/{id}/user-recs` | U RL | target_title_id, reason |
| PUT | `/user-recs/{id}/agree` | U | |
| GET | `/me/recommendations?limit=` | U | Falls back to cold-start for new users |
| POST | `/events` | — or U, RL | Batched client events, schema-validated |

## Caching (Redis)

| Key pattern | TTL | Invalidated by |
|---|---|---|
| `title:{id}` | 1 h | Title update or catalog import |
| `explore:top:{media_type}:{sort}`, `explore:trending:{media_type}:{window}` | Until the next scheduled recompute | Recompute job |
| `similar:{id}` | 24 h | Recommender training job |
| `recs:user:{user_id}` | 24 h | Change to the user's list or score; training job |

Search responses are not cached in Redis, because Meilisearch is already fast enough.

Never cache responses that contain private user data under keys that are not user-scoped.
