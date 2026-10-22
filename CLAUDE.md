# CLAUDE.md

Instructions for AI agents and developers working in this repository. Read this first, then the doc routed for your task.

## Project

This is a movie discovery, tracking, and recommendation website: search, explore, a personal watch list with status and score, reviews, personalized and community recommendations, and SEO-friendly public pages.

- **Target**: a modular monolith with a Next.js frontend, a FastAPI backend, PostgreSQL + pgvector, Redis (Valkey), Meilisearch, and a Taskiq worker.
- **Today**: the Phase 0 skeleton of that stack exists (health endpoint, migrations, worker, compose, CI). No product features exist yet. A legacy Streamlit prototype (content-based recommender over TMDB 5000) is still in the root.

Never describe planned components as implemented. Check the filesystem first.

## Repository map (verified 2026-10-22)

| Path | What it is |
|---|---|
| `pyproject.toml`, `uv.lock` | uv workspace root (members `apps/api`, `ml`; ADR-026). One `.venv` at the root |
| `apps/api/` | FastAPI + Taskiq worker (uv, Python 3.12): `app/core`, `app/modules/health`, `app/integrations` (optional TMDB client), `app/workers`, `alembic/`, `tests/`, `openapi.json` |
| `apps/web/` | Next.js 16 (pnpm, Node 24): placeholder home page, `src/features/titles` Poster, `src/lib/api` generated client, Vitest. Read `apps/web/AGENTS.md` before writing Next.js code |
| `ml/` | Package `movie-ml`: pure offline recommender code imported by worker tasks; never imports `app` or the DB. Empty so far |
| `infra/docker-compose.yml` | Local stack: db, redis, meili, migrate, api, worker, scheduler, web |
| `.github/workflows/ci.yml` | CI for api (lint, types, tests, contract), ml (lint, types, tests) and web (lint, types, tests, build) |
| `app.py` | Legacy Streamlit UI; loads `artifacts/*.pkl`, fetches posters from TMDB |
| `Movie Recommender System Data Analysis.ipynb` | Legacy pipeline: TMDB CSV → CountVectorizer → cosine matrix → pickle |
| `requirements.txt` | Legacy prototype deps only (pip) |
| `start.sh` | Legacy PaaS launcher for Streamlit |
| `data/`, `artifacts/` | Gitignored inputs/outputs. `data/` holds the TMDB 5000 CSVs (the catalog source, ADR-023); `artifacts/` is empty, pickles must be regenerated |
| `.claude/docs/` | Design and process docs (routing below) |

Not built yet: domain modules and tables, auth, search indexing, CSV catalog import, `ml/` pipelines, production deploy. The target layout, with current/planned markers, is in [architecture.md](.claude/docs/architecture.md).

## Documentation routing

Read the listed doc before starting the task. Read several when a task spans areas.

| Task | Read first |
|---|---|
| Understanding what exists, legacy code, migrating or removing it | [current-state.md](.claude/docs/current-state.md) |
| Adding modules, folders, services; frontend/backend structure | [architecture.md](.claude/docs/architecture.md) |
| Choosing a library or tool, or anything touching an open question | [decisions.md](.claude/docs/decisions.md) |
| Tables, columns, indexes, Alembic migrations | [data-model.md](.claude/docs/data-model.md) |
| Endpoints, request/response shapes, errors, pagination, caching | [api-contracts.md](.claude/docs/api-contracts.md) |
| Recommendation algorithms, training jobs, evaluation | [recommendation.md](.claude/docs/recommendation.md) |
| Auth, cookies, tokens, CSRF, authorization, rate limits, secrets, env vars | [security.md](.claude/docs/security.md) |
| Writing or running tests; definition of done | [testing.md](.claude/docs/testing.md) |
| Docker, CI/CD, VPS, monitoring, backups and restore | [deployment.md](.claude/docs/deployment.md) |
| Branches, commits, PRs | [git-workflow.md](.claude/docs/git-workflow.md) |

## Core rules

- **Modular monolith.** One FastAPI app with domain modules, one worker from the same codebase. Do not add services without a new ADR in `decisions.md`.
- **Backend layering:** router → service → repository. No SQL in routers. Pydantic schemas at every boundary; never return ORM objects.
- **Schema changes** go through an Alembic migration in the same commit.
- **Media types:** the catalog is `titles` + `media_type` (movies first). Reference `title_id`; shared tables, API schemas, and components must not assume `movie` (per-type URL prefixes like `/movie/...` are fine) ([data-model.md](.claude/docs/data-model.md)).
- **Search** is a core feature and runs on Meilisearch from Phase 1. Index settings live in code, not in manual config.
- **API changes** update `api-contracts.md`, re-export `apps/api/openapi.json`, and regenerate `apps/web/src/lib/api/schema.d.ts` in the same commit (CI checks both).
- **Background work** runs as Taskiq tasks in `app/workers/`, with one scheduler per environment.
- **Recommendations** are computed offline by the worker and stored in Postgres. The API only reads, filters, and re-ranks. Do not extend the pickle approach.
- **Catalog data** comes from the CSVs in `data/` through the `CatalogSource` importer (ADR-023). Never commit the CSVs.
- **Posters** are optional (ADR-025): TMDB is used only for `poster_path`, through `app/integrations/tmdb_client.py`, and only when `TMDB_API_KEY` is set. Without it, nothing calls TMDB and the UI shows placeholders.
- **External calls** go only through an integration client, with timeouts and retries. Tests never hit third-party APIs.
- **Config** comes from typed settings (pydantic-settings), never from scattered `os.environ` reads.
- **Open questions** in `decisions.md`: do not silently pick an answer; ask. **New dependencies and images**: pin versions at least two weeks old (pnpm enforces this via `minimumReleaseAge`).
- **Docs stay true.** When you build something, move it from "planned" to "current" in the relevant doc in the same change.

## Existing code and change tracking

- Legacy files (`app.py`, notebook, `start.sh`, `requirements.txt`) may be modified or deleted, but only in a dedicated branch and commit, as described in [git-workflow.md](.claude/docs/git-workflow.md).
- Before deleting, check that nothing still needs the logic. Port it first (for example, the notebook pipeline → `ml/src/movie_ml/`), then name its new location in the commit body.
- Use `git mv` for moves. Never delete `data/` or `artifacts/` contents you did not create.
- For broad restructuring (many files moved or deleted at once), list the file operations and get confirmation first.

## Git

- Branch `<type>/<topic>` with type one of `feature`, `fix`, `hotfix`, `refactor`, `docs`, `chore`, `test`.
- Conventional Commits with a descriptive body (Summary / Changes / Rationale / Impact / Removed-moved files).
- Commit only when asked. Never push, force-push, or merge to `main` without explicit instruction.

## Security (non-negotiable)

- Never commit secrets, `.env`, `.streamlit/secrets.toml`, dumps, or production config. Use placeholders like `<TMDB_API_KEY>` in examples.
- Validate all input with Pydantic, and enforce authorization in the backend service layer. Writes act on the authenticated user only.
- Auth uses httpOnly cookies, rotating refresh tokens with reuse detection, and CSRF double-submit. Follow [security.md](.claude/docs/security.md) exactly.
- Rate-limit auth, search, write, and event endpoints.
- Never log passwords, tokens, cookies, or auth headers.
- No destructive database operations (drop, truncate, mass delete or update, destructive migration, restore over existing data) without explicit approval.

## Testing expectations

- A task is done only when the checks in [testing.md](.claude/docs/testing.md) "Definition of done" pass. Report failures with their real output.
- CI must stay green. When a new stack is added (for example `ml/`), it adds its own lint, typecheck, and test commands to CI, `testing.md`, and this file.
- Use a real Postgres for backend tests (no SQLite). New endpoints need success and authorization tests.

## Commands

Details: [testing.md](.claude/docs/testing.md), [deployment.md](.claude/docs/deployment.md).

```bash
cp infra/.env.example infra/.env && docker compose -f infra/docker-compose.yml up -d --build
uv sync --all-packages                                                # once, from the repo root: one .venv for api + ml
cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
cd apps/api && uv run python -m scripts.export_openapi openapi.json   # after API changes
cd ml && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
cd apps/web && pnpm gen:api && pnpm lint && pnpm typecheck && pnpm test && pnpm build
```

Legacy (needs CSVs in `data/`, the notebook re-run, and `.streamlit/secrets.toml` with a `[tmbd]` section): `pip install -r requirements.txt && streamlit run app.py`.

## Working style

- Be technical and direct.
- Stop only processes you started, by their PID. Never use broad kill filters.
- Read the code and the routed doc before editing. Prefer small, reviewable changes.
- Verify claims against the repository. If something is unknown or undecided, say so instead of guessing.
