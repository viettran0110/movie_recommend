# Architecture

Status:
- **Phase 0 skeleton is current**: `apps/api` (core, health module, Alembic, Taskiq worker), `apps/web` (Next.js, typed API client), `infra/docker-compose.yml`, CI, and the root uv workspace with an empty `ml/` package (ADR-026).
- **Current since Phase 1 started**: the catalog tables (`app/modules/titles/models.py`) and the CSV catalog import (`app/modules/catalog`).
- **Planned**: every other domain module, the `ml/` pipelines, production infrastructure.
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
                           (CSV catalog import, reindex, train recs,
                            trending/top, email)
```

## Data flows

- **Read path (movie page)**:
  1. Next.js server component calls `GET /api/v1/titles/{id}`.
  2. The API checks the Redis cache, falls back to Postgres, then populates the cache.
  3. Posters are optional (ADR-025). When `poster_path` is set, the `Poster` component renders the TMDB CDN image (`https://image.tmdb.org/t/p/<size><poster_path>`); otherwise it renders a generated placeholder. Images are never stored locally.
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
- **Ingestion** (current, ADR-023; steps 3 and 7 planned):
  1. Source: the TMDB 5000 CSVs in the repository-root `data/` directory (gitignored, never committed). `tmdb_5000_movies.csv` and `tmdb_5000_credits.csv` are joined on `id` = `movie_id`. Nested columns (genres, keywords, cast, crew, companies, countries, languages) hold JSON arrays and are parsed with `json.loads`, not `ast.literal_eval`.
  2. An on-demand Taskiq task `catalog.import` (also runnable as `python -m scripts.import_catalog`) reads rows through a `CatalogSource`, validates each one into source-agnostic Pydantic records (`app/modules/catalog/schemas.py`), and upserts titles (with `movie_details`), genres, keywords, people, and credits keyed on (`media_type`, `tmdb_id`) and TMDB `credit_id`. It is idempotent: a conflicting row is updated only when a source column differs, so re-running unchanged data writes nothing; it never deletes, and never overwrites columns the source lacks (`poster_path`, `imdb_id`, ...). Invalid title rows are counted and logged by id, not fatal; an invalid nested item (one keyword, genre or credit) is dropped and logged, and its title is kept. Titles commit in batches of 500. The task returns an `ImportReport` (inserted, updated, unchanged, invalid, changed title ids). Type-specific detail rows go through a per-`media_type` registry (`DETAIL_SPECS` in `service.py`).
  3. (Planned, with Meilisearch) It then enqueues reindex jobs for `changed_title_ids`.
  4. There is no scheduled sync. The catalog changes only when the CSVs change and the import is re-run.
  5. `CatalogSource` is the extension point: `Tmdb5000CsvSource` is the only implementation. A TMDB API source, or a source for another `media_type` (ADR-019), plugs in behind the same interface.
  6. The directory comes from the `CATALOG_DATA_DIR` setting. In compose, `data/` is mounted read-only into the worker.
  7. Poster enrichment (planned, ADR-025): after an import, a Taskiq task `enrich_posters` runs only if `create_tmdb_client(settings)` returns a client, that is, if `TMDB_API_KEY` is set. It asks TMDB for the `poster_path` of each title whose `poster_path` is null and saves it, then invalidates `title:{id}` and enqueues reindex jobs. Without a key it logs that TMDB is disabled and exits. Adding a key later is the only step needed to get posters.

## Repository layout (target; `[current]` marks what exists)

```
pyproject.toml, uv.lock   [current] uv workspace root (members apps/api, ml; ADR-026); one .venv
apps/
  web/                    [current] Next.js 16 (App Router, TypeScript, Tailwind 4); shadcn/ui planned
    src/app/              routes: /, /movie/[id]-[slug] (one prefix per media_type), /search, /explore, /top,
                          /genre/[slug], /u/[username]/list, /login
    src/components/       shared UI (ui/ = shadcn primitives)
    src/features/<domain>/ domain components + hooks (titles, search, lists, auth, recs); [current] system/, titles/ (Poster)
    src/lib/api/          [current] openapi-fetch client + schema.d.ts generated from ../api/openapi.json — do not hand-edit
  api/                    [current] FastAPI
    app/main.py           [current] app factory + lifespan
    app/core/             [current] config, db, logging; [planned] security, cache
    app/modules/<domain>/ router.py, schemas.py, service.py, repository.py, models.py; [current] health/
    app/modules/titles/   [current] models.py (catalog ORM tables); [planned] read API (router, service, repository, schemas)
    app/modules/catalog/  [current] importer: schemas.py (records), service.py, repository.py (bulk upserts), sources/ (CatalogSource protocol, tmdb5000_csv.py)
    app/integrations/     [current] tmdb_client.py (optional poster paths, ADR-025); [planned] meili_client.py
    app/workers/          [current] Taskiq broker.py, scheduler.py, tasks.py (system.heartbeat, catalog.import)
    alembic/              [current] async env, revisions in versions/
    scripts/              [current] export_openapi.py → openapi.json (committed API contract), import_catalog.py
    tests/                [current] unit; fixtures/ (small TMDB 5000-shaped CSVs); integration/ (testcontainers)
ml/                       [current] package `movie-ml` (uv workspace member): pure offline code, imported by workers
  src/movie_ml/           [current] package root; [planned] content.py (TF-IDF similar, ADR-027), evaluation/
  tests/                  [current] boundary test (no app/DB/HTTP imports)
  notebooks/              [planned] legacy notebook moves here
infra/                    [current] docker-compose.yml (dev); [planned] prod compose, Caddyfile, monitoring
.github/workflows/        [current] ci.yml; [planned] deploy.yml
```

## Backend layering rules

- `router.py`: HTTP concerns only. It parses input into Pydantic schemas, calls the service, and returns schemas. No SQL, no ORM queries.
- `service.py`: business rules, authorization checks, transactions, and cache invalidation. It may call other modules' services, but never their repositories.
- `repository.py`: SQLAlchemy 2.0 async queries. Returns ORM objects or plain data.
- `schemas.py`: request/response models. Never return ORM objects directly.
- `models.py`: ORM tables. Every change requires an Alembic migration ([data-model.md](data-model.md)). Catalog tables are declared once in `titles/models.py`; the `catalog` module writes them through its own bulk-upsert repository, and `titles` reads them. New model modules must be imported in `alembic/env.py`.
- Offline ML code lives in `ml/` (`movie_ml`). It never imports `app`, so a worker task does the I/O: it loads rows through a repository, calls `movie_ml`, and writes the results through a repository (ADR-026).
- Config comes only from `app/core/config.py` (pydantic-settings). No `os.environ` lookups scattered through modules.
- External HTTP calls go through `app/integrations/`, with timeouts, retries, and backoff. That covers TMDB, used only for optional poster paths (ADR-025), and Meilisearch. The catalog is read from local files (ADR-023).

## Frontend rules

- Prefer server components for public pages (SEO). Use client components only for interactivity.
- Server state lives in TanStack Query on the client and in `fetch` with revalidate tags on the server. No global store unless one is justified.
- The API client is generated from FastAPI's OpenAPI schema (openapi-typescript + openapi-fetch). Regenerate it after API changes, and commit the result together with the API change.
- Validate forms with zod. The backend still validates everything; see [security.md](security.md).
- Use Tailwind + shadcn/ui primitives. No other component library.
- v1 is English only (ADR-020). Keep user-facing strings in one place per feature, not scattered literals, so next-intl can add Vietnamese later.
- Routes are prefixed by media type (`/movie/...`; `/tv/...` later). Shared components take a `media_type`-aware title object; do not hard-code "movie" in shared components.
