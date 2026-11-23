"""Catalog read API against a real PostgreSQL loaded from the CSV fixtures (requires Docker)."""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from asgi_lifespan import LifespanManager
from sqlalchemy import select

from app.core.config import Settings
from app.core.db import create_engine, create_session_factory
from app.main import create_app
from app.modules.catalog.service import import_catalog
from app.modules.catalog.sources.tmdb5000_csv import Tmdb5000CsvSource
from app.modules.titles.models import MediaType, Title

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "tmdb5000"


@pytest.fixture(scope="module")
async def title_ids(migrated_db_url: str) -> AsyncIterator[dict[int, int]]:
    """Imports the fixture catalog once; maps TMDB id (100, 200, 400) -> titles.id."""
    engine = create_engine(migrated_db_url)
    factory = create_session_factory(engine)
    await import_catalog(factory, Tmdb5000CsvSource(FIXTURES))
    async with factory() as session:
        rows = await session.execute(
            select(Title.tmdb_id, Title.id).where(Title.media_type == MediaType.MOVIE)
        )
        ids = {tmdb_id: title_id for tmdb_id, title_id in rows.all()}
    await engine.dispose()
    yield ids


@pytest.fixture
async def api(migrated_db_url: str, title_ids: dict[int, int]) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(Settings(app_env="test", database_url=migrated_db_url))
    async with LifespanManager(app) as manager:
        transport = httpx.ASGITransport(app=manager.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


async def test_get_title_returns_detail(api: httpx.AsyncClient, title_ids: dict[int, int]) -> None:
    title_id = title_ids[100]
    response = await api.get(f"/api/v1/titles/{title_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == title_id
    assert body["media_type"] == "movie"
    assert body["title"] == "Alpha Movie"
    assert body["slug"] == "alpha-movie"
    assert body["release_date"] == "2001-02-03"
    assert body["status"] == "released"
    assert body["tagline"] == "Go."
    assert body["tmdb_vote_avg"] == 7.2
    assert body["tmdb_vote_count"] == 150
    assert body["tmdb_popularity"] == 12.5
    assert body["poster_path"] is None
    assert body["score_avg"] is None
    assert (body["score_count"], body["members_count"]) == (0, 0)
    assert [g["name"] for g in body["genres"]] == ["Action", "Drama"]
    assert body["keywords"] == ["hero", "space"]
    assert body["movie"] == {"runtime": 120, "budget": 1_000_000, "revenue": 5_000_000}
    # Internal columns stay internal.
    assert not {"tmdb_id", "imported_at", "created_at", "updated_at"} & body.keys()


async def test_get_title_unknown_values_are_null(
    api: httpx.AsyncClient, title_ids: dict[int, int]
) -> None:
    body = (await api.get(f"/api/v1/titles/{title_ids[200]}")).json()

    assert body["release_date"] is None
    assert body["status"] == "post_production"
    assert body["movie"] == {"runtime": None, "budget": None, "revenue": None}


async def test_get_title_not_found_uses_error_envelope(api: httpx.AsyncClient) -> None:
    response = await api.get("/api/v1/titles/999999")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "not_found",
            "message": "Title not found",
            "details": {"title_id": 999999},
        }
    }


@pytest.mark.parametrize("bad_id", ["0", "-1", "abc", str(2**63)])
async def test_get_title_rejects_invalid_ids(api: httpx.AsyncClient, bad_id: str) -> None:
    response = await api.get(f"/api/v1/titles/{bad_id}")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_get_title_credits(api: httpx.AsyncClient, title_ids: dict[int, int]) -> None:
    response = await api.get(f"/api/v1/titles/{title_ids[200]}/credits")

    assert response.status_code == 200
    body = response.json()
    assert body["title_id"] == title_ids[200]
    assert [(c["person"]["name"], c["character"], c["order"]) for c in body["cast"]] == [
        ("Ann Actor", "Hero Again", 0)
    ]
    # Crew is sorted by job, then name.
    assert [(c["person"]["name"], c["job"]) for c in body["crew"]] == [
        ("Dee Director", "Director"),
        ("Wes Writer", "Screenplay"),
    ]


async def test_get_title_credits_orders_cast_by_billing(
    api: httpx.AsyncClient, title_ids: dict[int, int]
) -> None:
    body = (await api.get(f"/api/v1/titles/{title_ids[100]}/credits")).json()

    # An empty character in the CSV is null; crew outside the imported jobs is absent.
    assert [(c["person"]["name"], c["character"]) for c in body["cast"]] == [
        ("Ann Actor", "Hero"),
        ("Bob Actor", None),
    ]
    assert [c["job"] for c in body["crew"]] == ["Director"]


async def test_get_title_credits_not_found(api: httpx.AsyncClient) -> None:
    response = await api.get("/api/v1/titles/999999/credits")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_list_genres(api: httpx.AsyncClient) -> None:
    response = await api.get("/api/v1/genres")

    assert response.status_code == 200
    assert [(g["name"], g["slug"], g["media_types"]) for g in response.json()] == [
        ("Action", "action", ["movie"]),
        ("Comedy", "comedy", ["movie"]),
        ("Drama", "drama", ["movie"]),
    ]


async def test_list_genres_filters_by_media_type(api: httpx.AsyncClient) -> None:
    assert len((await api.get("/api/v1/genres?media_type=movie")).json()) == 3
    response = await api.get("/api/v1/genres?media_type=tv")
    assert response.status_code == 422


async def test_genre_titles_sorted_by_popularity(
    api: httpx.AsyncClient, title_ids: dict[int, int]
) -> None:
    response = await api.get("/api/v1/genres/drama/titles")

    assert response.status_code == 200
    body = response.json()
    assert (body["page"], body["page_size"], body["total"]) == (1, 20, 2)
    assert [t["id"] for t in body["items"]] == [title_ids[100], title_ids[200]]
    assert set(body["items"][0]) == {
        "id",
        "media_type",
        "slug",
        "title",
        "release_date",
        "poster_path",
        "tmdb_vote_avg",
        "tmdb_vote_count",
    }


async def test_genre_titles_paginates(api: httpx.AsyncClient, title_ids: dict[int, int]) -> None:
    page2 = (await api.get("/api/v1/genres/drama/titles?page=2&page_size=1")).json()
    assert (page2["total"], [t["id"] for t in page2["items"]]) == (2, [title_ids[200]])

    past_end = (await api.get("/api/v1/genres/drama/titles?page=3&page_size=1")).json()
    assert (past_end["total"], past_end["items"]) == (2, [])


@pytest.mark.parametrize(
    "query", ["page=0", "page_size=0", "page_size=101", "page=10001", "media_type=book"]
)
async def test_genre_titles_rejects_invalid_params(api: httpx.AsyncClient, query: str) -> None:
    response = await api.get(f"/api/v1/genres/drama/titles?{query}")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_genre_titles_unknown_genre(api: httpx.AsyncClient) -> None:
    response = await api.get("/api/v1/genres/no-such-genre/titles")

    assert response.status_code == 404
    assert response.json()["error"] == {
        "code": "not_found",
        "message": "Genre not found",
        "details": {"slug": "no-such-genre"},
    }
