# Testing

Status: **No tests or test tooling exist yet.** Every command below is **planned**. Each one becomes required from the change that introduces its tooling. When a command first works, update this file and [CLAUDE.md](../../CLAUDE.md) to mark it current.

## Backend (`apps/api`, planned)

- Use pytest with pytest-asyncio and httpx `AsyncClient` against the ASGI app.
- Use a real PostgreSQL with pgvector, started by testcontainers or the compose `db` service. **Do not use SQLite**, because the schema relies on enums, pgvector, and pg_trgm.
- Each test runs in a transaction that is rolled back at the end, or against a fresh schema created by running `alembic upgrade head`.
- Required test coverage:
  - Every endpoint: one success case and its main error cases (401, 403, 404, 422).
  - Authorization: user A cannot modify user B's data.
  - Auth: refresh rotation, reuse detection, logout revocation, CSRF rejection.
  - Migrations: `alembic upgrade head`, then `downgrade -1`, then `upgrade head`, on an empty database.
- Mock external services (TMDB) at the `app/integrations/` boundary. Tests never call TMDB.

```bash
cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest
```

## Frontend (`apps/web`, planned)

- Lint, typecheck, and unit tests (Vitest + Testing Library) for components that contain logic.
- Playwright e2e for the critical path: register → search → open movie → add to list with a score → see it on `/u/{username}/list` → `/me/recommendations` returns items.

```bash
cd apps/web && pnpm lint && pnpm typecheck && pnpm test && pnpm e2e
```

## Recommender (`ml/`, planned)

- Unit tests for the metric functions (Recall@K, NDCG@K) on small hand-computed fixtures.
- An offline evaluation report compared against the popularity baseline. This is a gate before a model change ships ([recommendation.md](recommendation.md)).

```bash
uv run python -m ml.pipelines.train --eval
```

## Definition of done

| Change type | Required |
|---|---|
| Backend code | Lint + typecheck + pytest pass; new or changed endpoint has tests; docs updated if the contract changed |
| Model / schema | Alembic migration included and tested up/down; [data-model.md](data-model.md) updated |
| Frontend | Lint + typecheck + unit tests pass; e2e passes if the critical path is touched; API client regenerated if the API changed |
| Recommender | Eval report beats the baseline; `model_version` bumped |
| Docs only | Links resolve; CLAUDE.md ≤ 150 lines |
| Legacy Streamlit (until removed) | `streamlit run app.py` starts, given local artifacts; nothing automated exists |

Never mark a task done while tests are failing. Report failures with the actual output.
