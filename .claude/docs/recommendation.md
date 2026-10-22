# Recommendation

Status: tier 0 is **Current** (legacy prototype). Every other tier is **Planned**. Implement the tiers in order, and do not ship a tier unless it beats the previous one in offline evaluation.

**MVP scope (ADR-015, independent of MovieLens):**
- Tier 1: Bayesian top and time-decayed trending.
- Tier 2: content-based on catalog metadata (from the TMDB 5000 CSVs, ADR-023).
- User ratings, list, and status tracking ([data-model.md](data-model.md)).

Tiers 3–5 require interaction data from this site's own users and start only once the threshold in "Data sources" is met.

All tiers work on `titles` and are media-type aware: similar items stay within the same `media_type` unless a rule explicitly allows mixing (ADR-019).

## Tier 0 — current prototype

The pipeline is a content-based CountVectorizer over the tags overview, genres, keywords, top-3 cast, and director, followed by a dense cosine similarity matrix pickled to `artifacts/` (see [current-state.md](current-state.md)). Replace it in Phase 1 with tier 2 stored in Postgres. Do not extend the pickle approach.

## Serving architecture (planned)

- **Offline**: the worker runs the code in `ml/pipelines/` on a schedule. Results go to `title_embeddings`, `item_similarities`, and `user_recommendations` ([data-model.md](data-model.md)), and every row carries a `model_version`.
- **Online**: the `recommendations` module in the API reads those tables, removes items already in the user's list, re-ranks, attaches a reason, and caches the result.
- The API process never trains models or loads training data.

## Tiers

### 1. Non-personalized (guests, cold start, explore pages)

- **Top rated**: Bayesian weighted rating `WR = v/(v+m)·R + m/(v+m)·C`.
  - R: the title's mean score.
  - v: its vote count.
  - m: the minimum-vote threshold. Start at the 80th percentile of `score_count` and tune it.
  - C: the global mean score.
- **Popular**: `members_count`.
- **Trending**: `Σ w_type · e^(−λ·Δt_hours)` over recent events from `title_stats_daily`/`user_events`, recomputed hourly. Start with half-life = 72 h.

### 2. Content-based (detail page "Similar", new items)

- **Chosen for Phase 1 (ADR-027):** TF-IDF per field with weights (genres, keywords, director, top cast, overview) instead of one concatenated bag of words. Code lives in `ml/` (`movie_ml`, ADR-026); the worker stores the top-K neighbours in `item_similarities`.
- **Later, as a new `model_version`:** sentence-transformers embeddings on title + overview (`all-MiniLM-L6-v2`, 384 dims; switch to a multilingual-e5 model when Vietnamese is added, per ADR-020), stored in pgvector and queried with HNSW kNN. It must beat the TF-IDF version before it ships.
- Combine with metadata overlap (genres, director) as a blended score.
- **Evaluation before interaction data exists:** the popularity-baseline gate below needs site interactions, which do not exist yet. Until they do, a tier-2 model ships with a sanity report instead: genre overlap@10 against random and popularity neighbours, plus hand-checked examples, recorded in the PR.

### 3. Collaborative filtering (personalized "For you", post-MVP)

- **Item-item CF**: cosine or Jaccard similarity over the user×item matrix built from `user_title_entries`. It is explainable: "Because you watched X".
- **ALS / BPR** (`implicit`) on implicit feedback. Starting confidence weights, to be tuned:

  | Signal | Weight |
  |---|---|
  | completed | 4 |
  | watching | 3 |
  | score ≥ 8 | +2 |
  | plan_to_watch | 1.5 |
  | on_hold | 1 |
  | view event | 0.5 |
  | dropped | 0 (and exclude from recs) |

- The minimum activity before switching a user from cold start to CF is about 10 interactions. Tune this threshold.

### 4. Community recommendations

`user_rec_submissions` ("if you liked A, watch B"), ranked by agreement count. Shown on the detail page and used as a candidate source.

### 5. Hybrid (later)

- **Candidate generation**: union of ALS, item-CF, content, trending, and community sources, about 200–500 per user.
- **Ranker**: LightGBM LambdaRank. Features: score from each source, the user's genre affinity, popularity, release year, recency.
- **Re-ranking**:
  - Remove items already in the user's list.
  - Apply MMR diversity (λ ≈ 0.7).
  - Cap the number of items per franchise.
  - Lightly boost new releases.
- Store `reason` for explanations.

## Cold start

- **New user**: onboarding asks for 3–5 genres and rates about 10 popular titles. Serve genre-filtered tier 1 plus tier 2 seeded from the rated items until the CF threshold is reached.
- **New item**: tier 2 only, until it has interactions.

## Evaluation (required before switching models)

- Split by time: train on interactions before T, test on each user's interactions after T (leave-last-N-out).
- Metrics: Recall@10, NDCG@10, MAP@10, catalog coverage, intra-list diversity, novelty.
- Baseline: popularity. A model must beat it on Recall@10 and NDCG@10 without collapsing coverage.
- Record results with their `model_version` in the PR description. MLflow is optional.
- Online metrics: recommendation CTR and add-to-list rate from `user_events`. Compare model versions with an A/B split by user id hash.

## Data sources

- **Catalog features** come from the TMDB 5000 CSVs imported into the catalog tables: genres, keywords, credits, overview, popularity, and vote counts (ADR-023). Training reads the tables, never the CSVs directly.
- **Interactions** come only from this site: `user_title_entries` (status, score) and `user_events`.
- **No external rating datasets.** MovieLens is not used, not even for experiments (ADR-015). Offline evaluation runs on the site's own interaction logs.
- **Before real data exists**: tier 1 rankings use TMDB `tmdb_vote_avg`/`tmdb_vote_count` as the R and v inputs, then blend toward site scores as `score_count` grows.
- **CF activation threshold** (tune it): about 500 active users and about 20k entries in total. Below that, "For you" is built from content similarity to the user's highly scored and completed titles, filtered by genre affinity.
