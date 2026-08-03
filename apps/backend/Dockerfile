FROM python:3.12-slim-bookworm AS base

COPY --from=ghcr.io/astral-sh/uv:0.11.18 /uv /uvx /bin/

# UV_NO_CACHE: без него в образе лежат две копии каждого пакета — кеш uv и сам
# venv, потому что link-mode=copy именно копирует. На образе воркера это лишние
# 5,6 ГБ. Пересборку кеш всё равно не ускоряет: слой RUN строится целиком.
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_CONCURRENT_DOWNLOADS=2 \
    UV_CONCURRENT_BUILDS=1 \
    UV_CONCURRENT_INSTALLS=2 \
    PATH="/opt/venv/bin:${PATH}"

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY pipeline_contracts ./pipeline_contracts


FROM base AS backend

RUN uv sync \
    --frozen \
    --only-group backend \
    --no-install-project

RUN mkdir -p \
    /app/apps/backend/alembic \
    /app/apps/backend/src


FROM base AS worker

# opencv приезжает с ultralytics и на `import cv2` линкуется к системным
# libGL и libglib — в slim-образе их нет, падает на импорте. Всё остальное,
# включая libgomp, torch несёт в своих колёсах.
RUN apt-get update \
    && apt-get install --no-install-recommends --yes \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Воркер — это бэкенд, который умеет ещё и считать: он держит сессию к базе,
# сам забирает задачи и сам регистрирует артефакты, а пайплайн только вызывает.
# Поэтому обе группы, а не одна `ml`.
#
# CUDA сюда ставить не нужно и нечем: её пользовательская часть приезжает
# колёсами nvidia-* вместе с torch, а драйвер живёт на хосте и пробрасывается
# внутрь nvidia-container-toolkit'ом. Подробности — в AGENTS.md §4.
RUN uv sync \
    --frozen \
    --only-group backend \
    --only-group ml \
    --no-install-project

RUN mkdir -p \
    /app/apps/backend/src \
    /app/ml \
    /app/models
