# Architecture

Status: **Planned** — none of the components below exist yet. Current code is the Streamlit prototype ([current-state.md](current-state.md)). Rationale for each choice: [decisions.md](decisions.md).

## Style

This is a modular monolith:
- One FastAPI application, split into domain modules.
- One worker process, running from the same codebase.
- One Next.js frontend.

Modules talk to each other through service functions, not over HTTP. Split a module into its own service only when it has a measured scaling or deployment need.

## Components

```
Cloudflare (DNS/CDN)
        │
     Caddy (TLS, reverse proxy)
   ┌────┴──────────────┐
Next.js (web)      FastAPI (api, /api/v1)
SSR/ISR, UI         modules: auth, users, movies, search,
   │                lists, reviews, recommendations
   └── REST/JSON ──▶    │          │            │
                  PostgreSQL   Redis/Valkey   Meilisearch
                  +pgvector    cache, rate    movie index
                  +pg_trgm     limit, broker
                       ▲          │
                       └── Dramatiq worker + APScheduler
                           (TMDB sync, reindex, train recs,
                            trending/top, email)
```

## Data flows

- **Read path (movie page)**:
  1. Next.js server component calls `GET /api/v1/movies/{id}`.
  2. The API checks the Redis cache, falls back to Postgres, then populates the cache.
  3. Posters are served from the TMDB image CDN via `next/image`. They are never stored locally.
- **Search**:
  1. Postgres is the source of truth.
  2. Writes to `movies` enqueue `reindex_movie(id)`, and the worker upserts into Meilisearch.
  3. The frontend queries `/api/v1/search`. Direct Meili access from the browser is allowed only with a search-only key.
- **Recommendations**:
  1. Offline: the worker trains on a schedule and writes results to Postgres (`movie_embeddings`, `item_similarities`, `user_recommendations`).
  2. Online: the API reads those tables, filters, re-ranks, and caches the result.
  3. The API never trains models or loads large artifacts into memory.
  4. Details: [recommendation.md](recommendation.md).
- **Ingestion**:
  1. A scheduled job pulls TMDB changes, then upserts movies, credits, and genres.
  2. It then enqueues reindex jobs.
  3. The data source decision is still open; see [decisions.md](decisions.md).

## Target repository layout (planned)

```
apps/
  web/                    Next.js (App Router, TypeScript, Tailwind, shadcn/ui)
    src/app/              routes: /, /movies/[id]-[slug], /search, /explore, /top,
                          /genre/[slug], /u/[username]/list, /login
    src/components/       shared UI (ui/ = shadcn primitives)
    src/features/<domain>/ domain components + hooks (movies, lists, auth, recs)
    src/lib/api/          generated OpenAPI client — do not hand-edit
  api/                    FastAPI
    app/main.py
    app/core/             config (pydantic-settings), db, security, logging, cache
    app/modules/<domain>/ router.py, schemas.py, service.py, repository.py, models.py
    app/integrations/     tmdb_client.py, meili_client.py
    app/workers/          Dramatiq actors, scheduler.py
    alembic/
    tests/
ml/                       offline training/evaluation, imported by workers
  notebooks/  recsys/  evaluation/  pipelines/
infra/                    docker-compose*.yml, Caddyfile, monitoring config
.github/workflows/
```

## Backend layering rules

- `router.py`: HTTP concerns only. It parses input into Pydantic schemas, calls the service, and returns schemas. No SQL, no ORM queries.
- `service.py`: business rules, authorization checks, transactions, and cache invalidation. It may call other modules' services, but never their repositories.
- `repository.py`: SQLAlchemy 2.0 async queries. Returns ORM objects or plain data.
- `schemas.py`: request/response models. Never return ORM objects directly.
- `models.py`: ORM tables. Every change requires an Alembic migration ([data-model.md](data-model.md)).
- Config comes only from `app/core/config.py` (pydantic-settings). No `os.environ` lookups scattered through modules.
- External HTTP calls (TMDB) go through `app/integrations/`, with timeouts, retries, and backoff.

## Frontend rules

- Prefer server components for public pages (SEO). Use client components only for interactivity.
- Server state lives in TanStack Query on the client and in `fetch` with revalidate tags on the server. No global store unless one is justified.
- The API client is generated from FastAPI's OpenAPI schema (openapi-typescript + openapi-fetch). Regenerate it after API changes, and commit the result together with the API change.
- Validate forms with zod. The backend still validates everything; see [security.md](security.md).
- Use Tailwind + shadcn/ui primitives. No other component library.
- i18n (next-intl, vi/en) is an open question; keep user-facing strings easy to extract.
