# Deployment and Operations

Status: **Planned.** The repository has no Docker, CI, or infrastructure config today. The only existing deploy artifact is the legacy [start.sh](../../start.sh), a PaaS-style Streamlit launcher. Decisions: ADR-011 and ADR-016 in [decisions.md](decisions.md).

## Local development (planned `infra/docker-compose.yml`)

| Service | Image / source | Port |
|---|---|---|
| `db` | `pgvector/pgvector:pg17` | 5432 |
| `redis` | `redis:7` or `valkey/valkey:8` | 6379 |
| `meili` | `getmeili/meilisearch` (pinned version) | 7700 |
| `api` | `apps/api` Dockerfile, uvicorn `--reload` | 8000 |
| `worker` | same image as api, runs the job worker (Q4) + scheduler | — |
| `web` | `apps/web`, `pnpm dev` | 3000 |

Pin image versions; never use `latest`. Secrets come from a local `.env` that is gitignored ([security.md](security.md) has the variable list).

## Production (planned)

- One VPS running Docker Compose (`infra/docker-compose.prod.yml`), with Caddy for TLS and reverse proxy, behind Cloudflare DNS/CDN.
- The Next.js app (`next start`, standalone output) runs on the same VPS (ADR-016). Caddy routes `/api/*` to `api:8000` and everything else to `web:3000`. Meilisearch is not exposed publicly.
- Images are built in GitHub Actions and pushed to GHCR, tagged with the git SHA.
- Deploy: SSH to the VPS, `docker compose pull`, run migrations, `docker compose up -d`, then a health check on `GET /api/v1/health`. If the health check fails, roll back to the previous SHA tag.
- Migrations: run `alembic upgrade head` as a one-off container **before** starting the new API. Destructive migrations need explicit approval and a fresh backup ([data-model.md](data-model.md)).
- Production secrets live in an environment file on the server (root-only, mode 600) or in GitHub Actions secrets. Never put them in the repository or in image layers.

## CI (planned `.github/workflows/`)

- `ci.yml` runs on PRs and pushes to `main`: the backend lint, typecheck, and tests, plus the frontend lint, typecheck, unit tests, and build ([testing.md](testing.md)).
- `deploy.yml` runs on `main` after CI passes: build, push to GHCR, deploy.
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
