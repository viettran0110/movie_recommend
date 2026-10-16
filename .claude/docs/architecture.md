# Architecture

Status:
- **Phase 0 skeleton is current**: `apps/api` (core, health module, Alembic, Taskiq worker), `apps/web` (Next.js, typed API client), `infra/docker-compose.yml`, CI.
- **Planned**: every domain module, `ml/`, production infrastructure.
- Markers in the layout below show which is which. What exists today is listed in [current-state.md](current-state.md). Rationale for each choice: [decisions.md](decisions.md).

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
SSR/ISR, UI         modules: auth, users, titles, search,
   │                lists, reviews, recommendations
   └── REST/JSON ──▶    │          │            │
                  PostgreSQL   Redis/Valkey   Meilisearch
                  +pgvector    cache, rate    title index
                  +pg_trgm     limit, broker
                       ▲          │
                       └── Taskiq worker + Taskiq scheduler
                           (TMDB sync, reindex, train recs,
                            trending/top, email)
```

## Data flows

- **Read path (movie page)**:
  1. Next.js server component calls `GET /api/v1/titles/{id}`.
  2. The API checks the Redis cache, falls back to Postgres, then populates the cache.
  3. Posters are served from the TMDB image CDN via `next/image`. They are never stored locally.
- **Search**:
  1. Postgres is the source of truth.
  2. Writes to `titles` enqueue `reindex_title(id)`, and the worker upserts into Meilisearch.
  3. The frontend queries `/api/v1/search` for results and facets, and `/api/v1/search/suggest` for autocomplete (debounced to about 150 ms). Direct Meili access from the browser is allowed only with a search-only key.
  4. Search is a core feature (ADR-018). Index settings (searchable, filterable, and sortable attributes, ranking rules, typo tolerance, synonyms) are version-controlled in code and applied by a job. Changing a setting triggers a reindex.
- **Recommendations**:
  1. Offline: the worker trains on a schedule and writes results to Postgres (`title_embeddings`, `item_similarities`, `user_recommendations`).
  2. Online: the API reads those tables, filters, re-ranks, and caches the result.
  3. The API never trains models or loads large artifacts into memory.
  4. Details: [recommendation.md](recommendation.md).
- **Ingestion**:
  1. A scheduled job pulls TMDB changes, then upserts titles (with `movie_details`), credits, and genres.
  2. It then enqueues reindex jobs.
  3. Source: the full TMDB API (ADR-014).
     - Initial bulk import from TMDB daily ID exports, then a daily sync through the `/changes` endpoints.
     - Respect TMDB rate limits and show the TMDB attribution.
     - Only `movie` is ingested at launch; ingestion is keyed by `media_type` so other types can be added (ADR-019).

## Repository layout (target; `[current]` marks what exists)

```
apps/
  web/                    [current] Next.js 16 (App Router, TypeScript, Tailwind 4); shadcn/ui planned
    src/app/              routes: /, /movie/[id]-[slug] (one prefix per media_type), /search, /explore, /top,
                          /genre/[slug], /u/[username]/list, /login
    src/components/       shared UI (ui/ = shadcn primitives)
    src/features/<domain>/ domain components + hooks (titles, search, lists, auth, recs); [current] system/
    src/lib/api/          [current] openapi-fetch client + schema.d.ts generated from ../api/openapi.json — do not hand-edit
  api/                    [current] FastAPI
    app/main.py           [current] app factory + lifespan
    app/core/             [current] config, db, logging; [planned] security, cache
    app/modules/<domain>/ router.py, schemas.py, service.py, repository.py, models.py; [current] health/
    app/integrations/     tmdb_client.py, meili_client.py
    app/workers/          [current] Taskiq broker.py, scheduler.py, tasks.py
    alembic/              [current] async env, revisions in versions/
    scripts/              [current] export_openapi.py → openapi.json (committed API contract)
    tests/                [current] unit; integration/ (testcontainers)
ml/                       offline training/evaluation, imported by workers
  notebooks/  recsys/  evaluation/  pipelines/
infra/                    [current] docker-compose.yml (dev); [planned] prod compose, Caddyfile, monitoring
.github/workflows/        [current] ci.yml; [planned] deploy.yml
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
- v1 is English only (ADR-020). Keep user-facing strings in one place per feature, not scattered literals, so next-intl can add Vietnamese later.
- Routes are prefixed by media type (`/movie/...`; `/tv/...` later). Shared components take a `media_type`-aware title object; do not hard-code "movie" in shared components.
