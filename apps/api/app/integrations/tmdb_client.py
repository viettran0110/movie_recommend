"""TMDB API client (ADR-025).

Used only to look up image paths: the catalog itself comes from the CSVs in data/ (ADR-023).
The client is optional: `create_tmdb_client` returns None when no API key is configured, and
callers must then skip TMDB entirely.

Error messages never include request URLs, because a v3 API key travels in the query string.
"""

import asyncio
import logging
import re
from types import TracebackType
from typing import Literal, Self

import httpx
from pydantic import BaseModel, SecretStr, ValidationError, field_validator

from app.core.config import Settings

logger = logging.getLogger(__name__)

MediaType = Literal["movie", "tv"]

# TMDB image paths look like "/kqjL17yufvn9OVLyXYpvtyrFfak.jpg". Anything else is dropped so a
# bad response can never put an arbitrary URL into a page.
IMAGE_PATH_PATTERN = re.compile(r"/[A-Za-z0-9_-]+\.(?:jpg|jpeg|png)")

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_RETRY_AFTER_SECONDS = 30.0


class TmdbError(Exception):
    """A TMDB request failed after retries, or TMDB answered with an unexpected body."""


class TmdbAuthError(TmdbError):
    """TMDB rejected the API key (HTTP 401). Never retried."""


class _TitleImages(BaseModel):
    poster_path: str | None = None

    @field_validator("poster_path")
    @classmethod
    def _drop_unexpected_path(cls, value: str | None) -> str | None:
        if value is not None and not IMAGE_PATH_PATTERN.fullmatch(value):
            logger.warning("tmdb returned an unexpected poster_path format; ignoring it")
            return None
        return value


def _auth(api_key: str) -> tuple[dict[str, str], dict[str, str]]:
    """Return (headers, query params). v4 Read Access Tokens are JWTs; v3 keys are not."""
    if api_key.count(".") == 2:
        return {"Authorization": f"Bearer {api_key}"}, {}
    return {}, {"api_key": api_key}


class TmdbClient:
    def __init__(
        self,
        api_key: SecretStr,
        *,
        base_url: str = "https://api.themoviedb.org/3",
        timeout_seconds: float = 10.0,
        max_retries: int = 3,
        backoff_seconds: float = 0.5,
        max_concurrency: int = 8,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        headers, params = _auth(api_key.get_secret_value())
        self._http = httpx.AsyncClient(
            base_url=base_url,
            headers={"Accept": "application/json", **headers},
            params=params,
            timeout=httpx.Timeout(timeout_seconds),
            transport=transport,
        )
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds
        self._limit = asyncio.Semaphore(max_concurrency)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get_poster_path(self, media_type: MediaType, tmdb_id: int) -> str | None:
        """Poster path for a title, e.g. "/abc.jpg". None if TMDB has no title or no poster."""
        if tmdb_id <= 0:
            raise ValueError("tmdb_id must be positive")
        response = await self._get(f"/{media_type}/{tmdb_id}")
        if response is None:
            return None
        try:
            return _TitleImages.model_validate_json(response.content).poster_path
        except ValidationError:
            raise TmdbError("TMDB returned an unexpected response body") from None

    async def _get(self, path: str) -> httpx.Response | None:
        """GET with retries on timeouts, connection errors, 429 and 5xx. None on 404."""
        attempt = 0
        while True:
            try:
                async with self._limit:
                    response = await self._http.get(path)
            except httpx.TransportError as exc:
                if attempt >= self._max_retries:
                    raise TmdbError(f"TMDB unreachable ({type(exc).__name__})") from None
                await asyncio.sleep(self._delay(attempt, None))
                attempt += 1
                continue

            status = response.status_code
            if response.is_success:
                return response
            if status == 404:
                return None
            if status == 401:
                raise TmdbAuthError("TMDB rejected the API key (HTTP 401)")
            if status in RETRY_STATUSES and attempt < self._max_retries:
                await asyncio.sleep(self._delay(attempt, response.headers.get("Retry-After")))
                attempt += 1
                continue
            raise TmdbError(f"TMDB returned HTTP {status}")

    def _delay(self, attempt: int, retry_after: str | None) -> float:
        if retry_after is not None:
            try:
                return min(max(float(retry_after), 0.0), MAX_RETRY_AFTER_SECONDS)
            except ValueError:
                pass
        return float(self._backoff_seconds * 2**attempt)


def create_tmdb_client(settings: Settings) -> TmdbClient | None:
    """The configured client, or None when TMDB is disabled (no API key)."""
    if settings.tmdb_api_key is None:
        return None
    return TmdbClient(settings.tmdb_api_key, base_url=settings.tmdb_api_url)
