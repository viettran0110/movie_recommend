# Git Workflow

Status: **Current.** These rules apply now. Decision: ADR-012 in [decisions.md](decisions.md).

## Branches

Branch from `main`, named `<type>/<kebab-case-topic>`. Merge back to `main`. Branch names are not tied to roadmap phases.

| Type | Use for | Example |
|---|---|---|
| `feature/` | New user-facing or API capability | `feature/movie-search` |
| `fix/` | Bug fix found during normal development | `fix/duplicate-title-lookup` |
| `hotfix/` | Urgent fix for something broken on `main` or in production; merge as soon as it is verified | `hotfix/refresh-token-loop` |
| `refactor/` | Restructuring with no behavior change, including moving or removing legacy code | `refactor/remove-streamlit-app` |
| `docs/` | Documentation only | `docs/claude-md-and-agent-docs` |
| `chore/` | Tooling, deps, CI, config, repo housekeeping | `chore/docker-compose-dev` |
| `test/` | Adding or fixing tests only | `test/auth-refresh-rotation` |

- Never force-push `main`. Never rewrite published history.
- Keep branches short-lived. Rebase on or merge `main` before opening a PR.
- Do not push or merge unless the user asks.

## Commits

Use Conventional Commits: `<type>(<scope>): <imperative summary>`, with the summary at most 72 characters.

- **Types**: `feat`, `fix`, `refactor`, `perf`, `docs`, `test`, `build`, `ci`, `chore`, `revert`.
- **Scopes**: `api`, `web`, `ml`, `db`, `auth`, `search`, `recs`, `infra`, `legacy`, `repo`. Omit the scope when the change spans many areas.
- One logical change per commit. Do not mix a refactor and a feature, or formatting and logic, in one commit.
- Never commit secrets, `.env`, datasets (`data/*.csv`), model artifacts (`artifacts/*.pkl`), or dumps.

### Body template

```
<type>(<scope>): <summary>

Summary: what changed, in one or two sentences.

Changes:
- concrete change 1
- concrete change 2

Rationale: why this change, and the alternatives considered if relevant.

Impact: behavior or API changes, migrations to run, config/env vars added.

Removed/moved files: (required when files are deleted or moved)
- path/old -> path/new
- path/deleted (logic now lives in path/replacement)
```

Leave out the sections that do not apply, except "Removed/moved files", which is required whenever files are moved or deleted. Use `git mv` for moves so history follows the file.

### Examples

```
refactor(legacy): remove Streamlit prototype

Summary: Delete the Streamlit UI now that the Next.js detail page serves
similar-movie recommendations.

Removed/moved files:
- app.py (replaced by apps/web/src/app/movies/[id]/page.tsx and
  GET /api/v1/movies/{id}/similar)
- start.sh (replaced by infra/docker-compose.prod.yml)
```

```
feat(auth): add refresh token rotation with reuse detection

Changes:
- refresh_tokens table with family_id and replaced_by_id
- POST /auth/refresh rotates tokens; reuse revokes the family

Impact: new Alembic revision; new env var REFRESH_TOKEN_TTL_SECONDS.
```

## Pull requests

The PR description contains:
- Summary.
- Linked issue, if any.
- Changes.
- How it was tested: commands run and their results.
- Screenshots for UI changes.
- Migration and deploy notes.
- For recommender changes: the offline eval table.

The checklist follows [testing.md](testing.md) "Definition of done".
