# CLAUDE.md

Instructions for AI agents and developers working in this repository. Read this first, then the doc routed for your task.

## Project

This is a movie discovery, tracking, and recommendation website: search, explore, a personal watch list with status and score, reviews, personalized and community recommendations, and SEO-friendly public pages.

- **Today**: the repository contains only a legacy Streamlit prototype (a content-based recommender over TMDB 5000).
- **Target**: a modular monolith with a Next.js frontend, a FastAPI backend, PostgreSQL + pgvector, Redis, Meilisearch, and a background job worker (library TBD: Dramatiq or Taskiq). **This is planned; none of it exists yet.**

Never describe planned components as implemented. Check the filesystem first.

## Repository map (verified 2026-10-16)

| Path | What it is |
|---|---|
| `app.py` | Legacy Streamlit UI; loads `artifacts/*.pkl`, fetches posters from TMDB |
| `Movie Recommender System Data Analysis.ipynb` | Legacy pipeline: TMDB CSV → CountVectorizer → cosine matrix → pickle |
| `requirements.txt`, `setup.py`, `pyproject.toml`, `src/` | Legacy packaging; `src/` holds only empty `__init__.py` files |
| `start.sh` | Legacy PaaS launcher for Streamlit |
| `data/`, `artifacts/` | Gitignored inputs/outputs. **Empty locally**: CSVs and pickles must be regenerated |
| `.claude/docs/` | Design and process docs (routing below) |

Missing today: tests, CI, Docker, a database, an API, a frontend app, linters. The target layout (`apps/web`, `apps/api`, `ml/`, `infra/`) is **planned**; see [architecture.md](.claude/docs/architecture.md).

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
- **API changes** update `api-contracts.md`, and the generated TypeScript client is regenerated and committed alongside.
- **Recommendations** are computed offline by the worker and stored in Postgres. The API only reads, filters, and re-ranks. Do not extend the pickle approach.
- **External calls** (TMDB) go only through an integration client, with timeouts and retries. Tests never hit TMDB.
- **Config** comes from typed settings (pydantic-settings), never from scattered `os.environ` reads.
- **Open questions** in `decisions.md`: do not silently pick an answer. Use the documented default and say so, or ask.
- **Docs stay true.** When you build something, move it from "planned" to "current" in the relevant doc in the same change.

## Existing code and change tracking

- Legacy files (`app.py`, notebook, `start.sh`, `setup.py`, `requirements.txt`, `src/`) may be modified or deleted, but only in a dedicated branch and commit, as described in [git-workflow.md](.claude/docs/git-workflow.md).
- Before deleting, check that nothing still needs the logic. Port it first (for example, the notebook pipeline → `ml/recsys/`), then name its new location in the commit body.
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
- No test tooling exists yet. The first change that adds a stack (api/web/ml) also adds its lint, typecheck, and test commands, and updates `testing.md` and this file.
- Use a real Postgres for backend tests (no SQLite). New endpoints need success and authorization tests.

## Commands

Current (legacy; requires CSVs in `data/`, notebook re-run, and `.streamlit/secrets.toml` with a `[tmbd]` section):

```bash
pip install -r requirements.txt
streamlit run app.py
```

Planned (not yet available; see [testing.md](.claude/docs/testing.md) and [deployment.md](.claude/docs/deployment.md)):

```bash
docker compose -f infra/docker-compose.yml up        # local stack
cd apps/api && uv run pytest                          # backend checks
cd apps/web && pnpm lint && pnpm typecheck && pnpm test
```

## Working style

- Be technical and direct.
- Read the code and the routed doc before editing. Prefer small, reviewable changes.
- Verify claims against the repository. If something is unknown or undecided, say so instead of guessing.
