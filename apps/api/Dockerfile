# syntax=docker/dockerfile:1
# Build context is the repository root (uv workspace, ADR-026); see the root .dockerignore.
FROM ghcr.io/astral-sh/uv:0.11.9-python3.12-trixie-slim AS build
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/
COPY ml/pyproject.toml ml/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package movie-api --no-install-workspace
COPY ml ml
COPY apps/api apps/api
# --no-editable installs movie-ml into the venv, so the runtime image needs no ml/ sources.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package movie-api --no-editable

FROM python:3.12-slim-trixie AS runtime
RUN useradd --create-home --uid 10001 app
WORKDIR /app/apps/api
COPY --from=build --chown=app:app /app/.venv /app/.venv
COPY --from=build --chown=app:app /app/apps/api /app/apps/api
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
