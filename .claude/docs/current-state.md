# Current State and Gap Analysis

Status: **Current** — describes what exists in the repository as of 2026-10-16. Update this file whenever a gap is closed.

## Inventory: new stack (Phase 0, current)

| Path | Role | Notes |
|---|---|---|
| [apps/api/](../../apps/api/) | FastAPI service + Taskiq worker | Python 3.12, uv. Only endpoint: `GET /api/v1/health` (DB, Redis, Meilisearch). Alembic revision `0001` enables vector, pg_trgm, citext. No domain tables yet |
| [apps/api/openapi.json](../../apps/api/openapi.json) | API contract | Exported by `scripts/export_openapi.py`; source for the web client types |
| [apps/web/](../../apps/web/) | Next.js 16 frontend | Placeholder home page showing API status; typed openapi-fetch client; Vitest |
| [infra/docker-compose.yml](../../infra/docker-compose.yml) | Local stack | db, redis (Valkey), meili, migrate, api, worker, scheduler, web |
| [.github/workflows/ci.yml](../../.github/workflows/ci.yml) | CI | api, api-integration, web jobs |
| [.gitattributes](../../.gitattributes) | Line endings | LF in the repository |

## Inventory: legacy prototype

| Path | Role | Notes |
|---|---|---|
| [app.py](../../app.py) | Streamlit UI | Select a title → show 5 similar movies with posters |
| `Movie Recommender System Data Analysis.ipynb` | Offline pipeline | Builds `artifacts/*.pkl` from TMDB 5000 CSVs |
| [requirements.txt](../../requirements.txt) | Deps | `streamlit` + `-e .` (installs `setup.py`) |
| [setup.py](../../setup.py) | Packaging | Package `src/`; deps: streamlit, pandas, numpy, scikit-learn, requests; `python_requires>=3.7` |
| [pyproject.toml](../../pyproject.toml) | Build system only | setuptools backend, no project metadata |
| `src/__init__.py`, `src/utils/__init__.py` | Empty package | No code |
| [start.sh](../../start.sh) | PaaS launch | Writes `~/.streamlit/config.toml`, runs on `$PORT` |
| `data/` | Input CSVs (gitignored) | `tmdb_5000_movies.csv`, `tmdb_5000_credits.csv` — present locally (4,803 movies each, added 2026-10-18). Also the planned catalog source (ADR-023) |
| `artifacts/` | Model output (gitignored) | Expects `movie_list.pkl`, `similarity.pkl` — **not present locally** |
| [README.md](../../README.md) | Run instructions | venv + `streamlit run app.py` |

Not present yet: domain tables, auth, search indexing, CSV catalog import, recommender code (`ml/`), production deploy, monitoring, backups.

## How the prototype works

1. Notebook loads the TMDB 5000 Kaggle CSVs and merges movies with credits.
2. `ast.literal_eval` parses JSON-like columns. It extracts genres, keywords, top-3 cast, and director, and strips the spaces inside names.
3. Builds a `tags` string (overview + genres + keywords + cast + crew) and lowercases it.
4. Vectorizes the tags with `CountVectorizer(max_features=5000, stop_words='english')`, then computes `cosine_similarity` as a dense matrix (~4800 × 4800).
5. Pickles `new_df` (movie_id, title, tags) and the similarity matrix into `artifacts/`.
6. `app.py` loads both pickles and sorts the selected row for the top 5. For each result it calls the TMDB API to fetch the poster, using `st.secrets["tmbd"]["api_key"]` from `.streamlit/secrets.toml`.

## Running it (legacy)

```bash
pip install -r requirements.txt
# Place the Kaggle CSVs in data/, run the notebook to produce artifacts/*.pkl
# Create .streamlit/secrets.toml with:  [tmbd]\napi_key = "<TMDB_API_KEY>"
streamlit run app.py
```

The app fails at startup if `artifacts/*.pkl` is missing.

## Known issues

- The dense N×N similarity matrix grows O(N²) in memory and disk, so it does not scale beyond a few thousand titles.
- Pickle loading is unsafe for untrusted files, and the pickle is coupled to the pandas version.
- Every recommendation makes 5 TMDB HTTP calls, with no timeout and no error handling. `@st.cache_data` mitigates repeat calls only.
- `movies[movies['title'] == movie].index[0]` breaks on duplicate titles.
- The secret section is misspelled `tmbd` (it should be `tmdb`). Keep this in mind if the legacy app is reused.
- Dependencies are split between `requirements.txt` and `setup.py`, with no pinning and `python>=3.7`.
- `start.sh` disables XSRF protection.

## Gap vs target

| Capability | Current | Target (see [architecture.md](architecture.md)) |
|---|---|---|
| UI | Streamlit page; Next.js placeholder | Next.js SSR site |
| API | health endpoint only | FastAPI `/api/v1` ([api-contracts.md](api-contracts.md)) |
| Storage | pickle files; Postgres with extensions only | PostgreSQL + pgvector ([data-model.md](data-model.md)) |
| Search | selectbox over titles | Meilisearch |
| Users / lists / ratings | none | auth + `user_title_entries` ([security.md](security.md)) |
| Recommendation | content-based CountVectorizer | tiered hybrid ([recommendation.md](recommendation.md)) |
| Tests / CI / deploy | api + web tests and CI exist; no deploy | [testing.md](testing.md), [deployment.md](deployment.md) |

## Proposed legacy migration (not executed)

Legacy files may be modified or deleted (see [decisions.md](decisions.md) ADR-012). Each step happens in its own branch and commit per [git-workflow.md](git-workflow.md).

| Legacy | Proposed destination |
|---|---|
| Notebook | `git mv` → `ml/notebooks/` |
| Notebook pipeline logic | Re-implement in `ml/recsys/content.py` (TF-IDF/embeddings) |
| `app.py`, `start.sh` | Delete once the Next.js movie detail + similar movies feature replaces them |
| `setup.py`, `requirements.txt`, `pyproject.toml` (root), `src/` | Delete; replaced by `apps/api/pyproject.toml` (uv), which now exists |
| `data/`, `artifacts/` dirs | Keep as gitignored local dirs for ML inputs/outputs, or move under `ml/` |

## Roadmap (planned)

| Phase | Scope |
|---|---|
| 0 (done) | Monorepo skeleton, docker-compose (Postgres+pgvector, Valkey, Meilisearch), Alembic, Taskiq worker, lint, CI — done 2026-10-16 |
| 1 | CSV catalog import from `data/` (ADR-023, no posters per ADR-024), Meilisearch search (autocomplete, typo tolerance, facets), explore, detail page, Bayesian top, content-based "similar" |
| 2 | Auth, personal list (status/score), public profile list, reviews, favorites |
| 3 | Events, time-decayed trending, `/me/recommendations` (content-based on the user's list), user-submitted recs; item-CF / ALS only after the own-data threshold ([recommendation.md](recommendation.md)) |
| 4 | Production deploy, monitoring, backups, rate limiting, admin |
| 5 | Hybrid ranker, MMR, A/B testing, TV/anime scope |
