import logging
from collections.abc import Callable

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.core.logging import configure_logging
from app.integrations.tmdb_client import (
    TmdbAuthError,
    TmdbClient,
    TmdbError,
    create_tmdb_client,
)

# Fake credentials in the two TMDB formats (v3 key: 32 hex chars; v4 token: a JWT).
V3_KEY = "0123456789abcdef0123456789abcdef"
V4_TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0In0.c2lnbmF0dXJl"  # noqa: S105

Handler = Callable[[httpx.Request], httpx.Response]


def make_client(handler: Handler, api_key: str = V3_KEY) -> TmdbClient:
    return TmdbClient(
        SecretStr(api_key),
        backoff_seconds=0,
        transport=httpx.MockTransport(handler),
    )


def respond(*responses: httpx.Response) -> tuple[Handler, list[httpx.Request]]:
    """Handler that replays `responses` in order and records each request."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return responses[min(len(seen), len(responses)) - 1]

    return handler, seen


@pytest.mark.parametrize("value", [None, "", "   "])
def test_disabled_without_api_key(value: str | None) -> None:
    assert create_tmdb_client(Settings(app_env="test", tmdb_api_key=value)) is None


async def test_enabled_with_api_key() -> None:
    client = create_tmdb_client(Settings(app_env="test", tmdb_api_key=V3_KEY))
    assert isinstance(client, TmdbClient)
    await client.aclose()


async def test_returns_poster_path_and_sends_v3_key_as_query_param() -> None:
    handler, seen = respond(httpx.Response(200, json={"id": 19995, "poster_path": "/abc_1-X.jpg"}))

    async with make_client(handler) as client:
        assert await client.get_poster_path("movie", 19995) == "/abc_1-X.jpg"

    assert seen[0].url.path == "/3/movie/19995"
    assert seen[0].url.params["api_key"] == V3_KEY
    assert "Authorization" not in seen[0].headers


async def test_sends_v4_token_as_bearer_header() -> None:
    handler, seen = respond(httpx.Response(200, json={"poster_path": None}))

    async with make_client(handler, api_key=V4_TOKEN) as client:
        assert await client.get_poster_path("movie", 1) is None

    assert seen[0].headers["Authorization"] == f"Bearer {V4_TOKEN}"
    assert "api_key" not in seen[0].url.params


async def test_unknown_title_is_none() -> None:
    handler, _ = respond(httpx.Response(404, json={"status_code": 34}))

    async with make_client(handler) as client:
        assert await client.get_poster_path("movie", 999999999) is None


@pytest.mark.parametrize("path", ["https://evil.example/x.jpg", "/../x.jpg", "/x.gif", "abc.jpg"])
async def test_unexpected_poster_path_is_dropped(path: str) -> None:
    handler, _ = respond(httpx.Response(200, json={"poster_path": path}))

    async with make_client(handler) as client:
        assert await client.get_poster_path("movie", 1) is None


async def test_retries_rate_limit_and_server_errors() -> None:
    handler, seen = respond(
        httpx.Response(429, headers={"Retry-After": "0"}),
        httpx.Response(503),
        httpx.Response(200, json={"poster_path": "/ok.jpg"}),
    )

    async with make_client(handler) as client:
        assert await client.get_poster_path("movie", 1) == "/ok.jpg"

    assert len(seen) == 3


async def test_gives_up_after_retries_without_leaking_the_key() -> None:
    handler, seen = respond(httpx.Response(500))

    async with make_client(handler) as client:
        with pytest.raises(TmdbError) as excinfo:
            await client.get_poster_path("movie", 1)

    assert len(seen) == 4  # first try + 3 retries
    assert V3_KEY not in str(excinfo.value)


async def test_rejected_key_is_not_retried() -> None:
    handler, seen = respond(httpx.Response(401))

    async with make_client(handler) as client:
        with pytest.raises(TmdbAuthError):
            await client.get_poster_path("movie", 1)

    assert len(seen) == 1


async def test_retries_timeouts_then_fails() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectTimeout("timed out", request=request)

    async with make_client(handler) as client:
        with pytest.raises(TmdbError, match="ConnectTimeout") as excinfo:
            await client.get_poster_path("movie", 1)

    assert calls == 4
    assert V3_KEY not in str(excinfo.value)


async def test_malformed_body_raises() -> None:
    handler, _ = respond(httpx.Response(200, content=b"not json"))

    async with make_client(handler) as client:
        with pytest.raises(TmdbError):
            await client.get_poster_path("movie", 1)


def test_httpx_request_logs_are_suppressed() -> None:
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    try:
        configure_logging("INFO")
        assert not logging.getLogger("httpx").isEnabledFor(logging.INFO)
    finally:
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)
