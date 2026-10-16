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
| ADR-007 | Meilisearch as the only search engine | Accepted | Elasticsearch: too heavy to run for this catalog size |
| ADR-008 | Auth owned by FastAPI: JWT access token + rotating refresh token in httpOnly cookies ([security.md](security.md)) | Accepted | Auth.js: couples auth to Next.js and needs cross-verification with FastAPI |
| ADR-009 | Background jobs: Dramatiq + Redis, cron via APScheduler | Accepted (see Q4) | Celery: heavier configuration than these jobs need |
| ADR-010 | Recommender stack: pandas/polars, scikit-learn, implicit, sentence-transformers, later LightGBM ([recommendation.md](recommendation.md)) | Accepted | LightFM, Surprise: poorly maintained |
| ADR-011 | Deploy: Docker Compose on one VPS, Caddy, GHCR, GitHub Actions; Sentry + Prometheus/Grafana ([deployment.md](deployment.md)) | Accepted | AWS ECS/RDS: cost and complexity |
| ADR-012 | Legacy prototype files may be modified or deleted; every change is traced through typed branches and descriptive commits ([git-workflow.md](git-workflow.md)) | Accepted | Freezing legacy code in `legacy/`: not required by the owner |
| ADR-013 | Posters and images are served from the TMDB CDN, not stored | Accepted | — |

## Open questions

Do not implement anything that depends on these until they are resolved. Record the answer here as a new ADR.

| # | Question | Default if unanswered | Impact |
|---|---|---|---|
| Q1 | Catalog source: TMDB API (full catalog, daily sync) vs TMDB 5000 CSV only | TMDB API, seeded from popular titles | Ingestion jobs, catalog size |
| Q2 | Use MovieLens ratings to bootstrap collaborative filtering? Its license is **non-commercial / research** | Use only for offline experiments, not in production | CF quality before real users exist |
| Q3 | Frontend hosting: Vercel vs the same VPS | Same VPS | Deploy pipeline, cost |
| Q4 | Job queue: Dramatiq vs Taskiq (async-native) | Dramatiq | Worker code style |
| Q5 | Phase 1 search: Meilisearch from the start vs Postgres FTS first | Meilisearch | Phase 1 scope |
| Q6 | Scope: movies only vs TV/anime too (`media_type` column) | Movies only, schema leaves room | Data model |
| Q7 | Versions: Python 3.12, Node 22 LTS, pnpm | As listed | Tooling |
| Q8 | i18n (vi/en) in the MVP? | Later; keep strings extractable | Frontend |
