# API Contracts

Status: **Planned draft.** No API exists yet. FastAPI's generated OpenAPI schema becomes the source of truth once implemented. Keep this file as the human summary and update it in the same change.

## Conventions

- Base path `/api/v1`, JSON only, `snake_case` fields.
- Health check: `GET /api/v1/health` returns `{"status":"ok"}`. It checks DB and Redis connectivity.
- Pagination: `?page=1&page_size=20` (max 100) returns `{"items": [...], "page", "page_size", "total"}`. Use cursor pagination (`?cursor=`) for `user_events`-style feeds.
- Errors: `{"error": {"code": "string_slug", "message": "human readable", "details": {...}}}` with the matching HTTP status. Validation errors return 422, with `details` listing field errors.
- Auth: the access token comes from an httpOnly cookie ([security.md](security.md)). Mutating requests that use cookie auth must send the CSRF header.
- Ownership: every `/me/*` route acts only on the authenticated user. Never accept a `user_id` from the client for writes.
- Timestamps are ISO 8601 UTC.

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

| Method | Path | Auth |
|---|---|---|
| GET | `/movies/{id}` | — |
| GET | `/movies/{id}/credits` | — |
| GET | `/movies/{id}/similar` | — |
| GET | `/movies/{id}/reviews` | — |
| GET | `/movies/{id}/user-recs` | — |
| GET | `/explore/top?sort=score\|popularity\|members` | — |
| GET | `/explore/trending?window=day\|week` | — |
| GET | `/explore/upcoming` | — |
| GET | `/genres`, `/genres/{slug}/movies` | — |
| GET | `/search?q=&genre=&year_from=&year_to=&min_score=&sort=` | — RL |

## User data

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/me` | U | |
| PATCH | `/me` | U | Profile fields only |
| GET | `/users/{username}` | — | Public profile |
| GET | `/users/{username}/list?status=` | — | Excludes `is_private` entries unless the requester is the owner |
| PUT | `/me/list/{movie_id}` | U | Upsert status, score, dates, notes |
| DELETE | `/me/list/{movie_id}` | U | |
| GET | `/me/stats` | U | Counts by status, mean score, genre distribution |
| PUT/DELETE | `/me/favorites/{movie_id}` | U | |
| POST | `/movies/{id}/reviews` | U RL | One per user per movie |
| PATCH/DELETE | `/reviews/{id}` | owner or A | |
| PUT | `/reviews/{id}/vote` | U | |
| POST | `/movies/{id}/user-recs` | U RL | target_movie_id, reason |
| PUT | `/user-recs/{id}/agree` | U | |
| GET | `/me/recommendations?limit=` | U | Falls back to cold-start for new users |
| POST | `/events` | — or U, RL | Batched client events, schema-validated |

## Caching (Redis)

| Key pattern | TTL | Invalidated by |
|---|---|---|
| `movie:{id}` | 1 h | Movie update or ingestion job |
| `explore:top:{sort}`, `explore:trending:{window}` | Until the next scheduled recompute | Recompute job |
| `similar:{id}` | 24 h | Recommender training job |
| `recs:user:{user_id}` | 24 h | Change to the user's list or score; training job |

Never cache responses that contain private user data under keys that are not user-scoped.
