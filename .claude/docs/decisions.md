# Decision Log

Status: **Current** record of decisions. "Accepted" means agreed for the target architecture, not that it is implemented ([current-state.md](current-state.md)).

To change a decision, add a new entry that supersedes the old one. Do not silently edit an Accepted entry.

| ID | Decision | Status | Rejected alternatives (why) |
|---|---|---|---|
| ADR-001 | Modular monolith (one API + one worker codebase) | Accepted | Microservices: operational overhead with no scaling need |
| ADR-002 | Frontend: Next.js App Router + TypeScript + Tailwind + shadcn/ui + TanStack Query + zod | Accepted | — |
| ADR-003 | Backend: FastAPI + Pydantic v2 + SQLAlchemy 2.0 async (asyncpg) + Alembic + pydantic-settings | Accepted | — |
| ADR-004 | Python tooling: uv, ruff, mypy (or pyright), pytest | Accepted | pip + requirements.txt + setup.py: no lockfile, duplicated deps |
| ADR-005 | PostgreSQL with pgvector + pg_trgm | Accepted | Pickled dense similarity matrix: O(N²), unsafe loading |
| ADR-006 | Redis (or Valkey) for cache, rate limiting, and job broker | Accepted | — |
| ADR-007 | Meilisearch as the only search engine (see ADR-018 for timing) | Accepted | Elasticsearch: too heavy to run for this catalog size |
| ADR-008 | Auth owned by FastAPI: JWT access token + rotating refresh token in httpOnly cookies ([security.md](security.md)) | Accepted | Auth.js: couples auth to Next.js and needs cross-verification with FastAPI |
| ADR-009 | Background job library, with Redis as broker and APScheduler for cron | Superseded by ADR-021 | Celery: heavier configuration than these jobs need |
| ADR-010 | Recommender stack: pandas/polars, scikit-learn, sentence-transformers; later `implicit` and LightGBM ([recommendation.md](recommendation.md)) | Accepted | LightFM, Surprise: poorly maintained |
| ADR-011 | Deploy: Docker Compose on one VPS, Caddy, GHCR, GitHub Actions; Sentry + Prometheus/Grafana ([deployment.md](deployment.md)) | Accepted | AWS ECS/RDS: cost and complexity |
| ADR-012 | Legacy prototype files may be modified or deleted; every change is traced through typed branches and descriptive commits ([git-workflow.md](git-workflow.md)) | Accepted | Freezing legacy code in `legacy/`: not required by the owner |
| ADR-013 | Posters and images are served from the TMDB CDN, not stored | Accepted | — |
| ADR-014 | Catalog source: the **full TMDB API**, with an initial bulk import and a daily sync job | Accepted (Q1) | TMDB 5000 CSV: static and too small |
| ADR-015 | Recommendation is **independent of MovieLens**. It uses Bayesian rating for rankings, time-decayed trending, and content-based filtering on TMDB metadata; personal signals come only from this site's users (ratings, list status). Collaborative filtering waits until the site's own interaction data is sufficient | Accepted (Q2) | MovieLens bootstrap: non-commercial license, and the data is not ours |
| ADR-016 | Frontend runs on the **same VPS** as the API, behind Caddy | Accepted (Q3) | Vercel: a second platform and split deployment |
| ADR-017 | Versions: Python 3.12, Node 22 LTS, pnpm | Accepted (Q7); Node part superseded by ADR-022 | — |
| ADR-018 | **Meilisearch from Phase 1.** Search is a core feature: autocomplete, typo tolerance, filters and facets, custom ranking | Accepted (Q5) | Postgres FTS first: weak typo tolerance and autocomplete |
| ADR-019 | **Movies first, extensible schema.** The catalog root is `titles` with a `media_type` enum (only `movie` at launch); type-specific tables hang off it; user data references `title_id` ([data-model.md](data-model.md)) | Accepted (Q6) | A movies-only schema: a TV/anime expansion would require migrating user data |
| ADR-020 | **English only in v1.** Vietnamese comes later; keep UI strings centralized so next-intl can be added without rewrites | Accepted (Q8) | Building i18n in the MVP: scope |
| ADR-021 | **Taskiq** for background jobs: `RedisStreamBroker` (acknowledged, re-delivered on worker death) and `TaskiqScheduler` with cron labels; no APScheduler. Tasks are async and share the app's async SQLAlchemy/httpx code | Accepted (Q4) | Dramatiq: sync actors would need a second, sync DB access path |
| ADR-022 | **Node 24 LTS** (24.16.0 in Docker and CI) replaces Node 22. Reasons: Node 22 leaves LTS maintenance in April 2027, and Node 24 is the local runtime. Compatibility verified on 2026-10-16: Next.js 16.3.8 requires Node >= 20.9; lint, typecheck, unit tests, and production build pass on 24.16.0; the standalone runtime image serves pages | Accepted | Staying on Node 22: an upgrade would be needed within six months |

## Open questions

None at the moment. When one arises, add it here with a default and its impact. Do not implement anything that depends on an open question until it is resolved; record the answer as a new ADR.
