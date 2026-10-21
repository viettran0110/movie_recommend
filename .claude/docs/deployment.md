# Deployment and Operations

Status:
- **Current**: the local Docker Compose stack, Dockerfiles for api and web, and the CI workflow.
- **Planned**: production compose, Caddy, deploy workflow, monitoring, and backups.
- The legacy [start.sh](../../start.sh) is a PaaS-style Streamlit launcher and is not part of the new stack.

Decisions: ADR-011, ADR-016, ADR-021, ADR-022 in [decisions.md](decisions.md).

## Local development (current: [infra/docker-compose.yml](../../infra/docker-compose.yml))

```bash
cp infra/.env.example infra/.env        # fill placeholders; infra/.env is gitignored
docker compose -f infra/docker-compose.yml up -d --build
docker compose -f infra/docker-compose.yml logs -f api worker
docker compose -f infra/docker-compose.yml down        # keeps volumes; `down -v` deletes local data
```

| Service | Image / source | Host port |
|---|---|---|
| `db` | `pgvector/pgvector:0.8.7-pg17` | 127.0.0.1:5432 |
| `redis` | `valkey/valkey:8.1.10-alpine` | 127.0.0.1:6379 |
| `meili` | `getmeili/meilisearch:v1.54.3` | 127.0.0.1:7700 |
| `migrate` | api image, one-off `alembic upgrade head` | — |
| `api` | [apps/api/Dockerfile](../../apps/api/Dockerfile), uvicorn `--reload`, `app/` bind-mounted | 127.0.0.1:8000 |
| `worker` | api image, `taskiq worker` | — |
| `scheduler` | api image, `taskiq scheduler`; run **exactly one** per environment | — |
| `web` | [apps/web/Dockerfile](../../apps/web/Dockerfile) `dev` target, `src/` bind-mounted | 127.0.0.1:3000 |

- Pin image versions; never use `latest`. Pick versions at least two weeks old. When you change the Postgres tag, update `tests/integration/test_migrations.py` too.
- Ports bind to 127.0.0.1 only.
- `down -v` deletes the local database and search index. Run it only when you mean to.
- Images: api uses a uv build stage on Debian trixie and runs as a non-root user on `python:3.12-slim-trixie`. web runs the standalone Next.js server on `node:24.16.0-trixie-slim` as a non-root user.

## Production (planned)

- One VPS running Docker Compose (`infra/docker-compose.prod.yml`), with Caddy for TLS and reverse proxy, behind Cloudflare DNS/CDN.
- The Next.js app (`next start`, standalone output) runs on the same VPS (ADR-016). Caddy routes `/api/*` to `api:8000` and everything else to `web:3000`. Meilisearch is not exposed publicly.
- Images are built in GitHub Actions and pushed to GHCR, tagged with the git SHA.
- Deploy: SSH to the VPS, `docker compose pull`, run migrations, `docker compose up -d`, then a health check on `GET /api/v1/health`. If the health check fails, roll back to the previous SHA tag.
- Migrations: run `alembic upgrade head` as a one-off container **before** starting the new API. Destructive migrations need explicit approval and a fresh backup ([data-model.md](data-model.md)).
- Production secrets live in an environment file on the server (root-only, mode 600) or in GitHub Actions secrets. Never put them in the repository or in image layers.

## CI

- **Current**: [ci.yml](../../.github/workflows/ci.yml) runs on PRs and pushes to `main`. It has three jobs: `api`, `api-integration`, and `web`. Commands are in [testing.md](testing.md). It also fails when `openapi.json` or `schema.d.ts` is stale.
- **Planned**: `deploy.yml` runs on `main` after CI passes: build, push to GHCR, deploy.
- Use Dependabot or Renovate for dependency updates.

## Monitoring (planned)

| Concern | Tool |
|---|---|
| Errors | Sentry (FastAPI + Next.js). Scrub cookies and auth headers in `before_send` |
| Metrics | `prometheus-fastapi-instrumentator` scraped by Prometheus, shown in Grafana (or Grafana Cloud free tier) |
| Logs | Structured JSON (structlog or Loguru). Ship to Loki or Grafana Cloud. No secrets or tokens in logs |
| Uptime | Uptime Kuma (or Grafana synthetic check) on `/api/v1/health` and the homepage |
| Jobs | Log every job's start, end, duration, and outcome. Alert when the nightly training or the backup fails |

## Backups and restore (planned)

**Backup**
- Run `pg_dump -Fc` nightly from a cron or worker job. Name files `movie_<env>_<YYYYMMDD-HHMM>.dump`.
- Copy each dump off-server to S3-compatible storage (Cloudflare R2 or S3), using a bucket-scoped key that has no delete permission.
- Retention: 7 daily, 4 weekly, 6 monthly.
- Meilisearch and Redis are **not** backed up. Both are rebuilt from Postgres.
- Back up the server's `.env` separately, encrypted. Never put it in the same bucket unencrypted.

**Restore procedure** (destructive; requires explicit approval when the target is not empty)
1. Stop `api` and `worker`.
2. Download the chosen dump and verify its checksum.
3. Restore into a **new** database: `createdb movie_restore && pg_restore -d movie_restore --no-owner <file>.dump`.
4. Run `alembic current` against it to confirm the schema revision matches the deployed code. If it is older, run `alembic upgrade head`.
5. Switch `DATABASE_URL` to the restored database, or rename the databases during the maintenance window.
6. Start `api` and `worker`, then enqueue a full Meilisearch reindex and a cache flush.
7. Smoke-test the health check, a movie page, login, and a user list.

**Drill**: restore the latest backup into a scratch database once a month and record the result. A backup that has never been restored does not count as verified.
