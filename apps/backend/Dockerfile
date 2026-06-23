FROM python:3.12-slim-bookworm AS base

COPY --from=ghcr.io/astral-sh/uv:0.11.18 /uv /uvx /bin/

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_CONCURRENT_DOWNLOADS=2 \
    UV_CONCURRENT_BUILDS=1 \
    UV_CONCURRENT_INSTALLS=2 \
    PATH="/opt/venv/bin:${PATH}"

WORKDIR /app

COPY pyproject.toml uv.lock ./


FROM base AS backend

RUN uv sync \
    --frozen \
    --only-group backend \
    --no-install-project

RUN mkdir -p \
    /app/apps/backend/alembic \
    /app/apps/backend/src


FROM base AS worker

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        ffmpeg \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN uv sync --frozen --no-install-project

RUN mkdir -p \
    /app/apps/backend/alembic \
    /app/apps/backend/src \
    /app/ml/pipeline \
    /app/models
