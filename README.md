# AI Ad Backend

FastAPI backend сервиса анализа видео с наружной рекламой. Backend владеет
PostgreSQL, бизнес-логикой, публичным API, состоянием очереди обработки и
метаданными файлов в MinIO.

Соседние репозитории:

- `../ai_ad_frontend` — React + Vite интерфейс;
- `../ai_ad_ml` — ML-пайплайн и нативный processing worker.

ML worker не подключается к PostgreSQL. Он забирает задания и сообщает
прогресс через внутренний HTTP API backend, а большие видео и артефакты передаёт
напрямую через MinIO.

## Структура

```text
src/
├── domain/          чистая бизнес-логика
├── application/     сервисы, DTO и интерфейсы
├── infrastructure/  PostgreSQL, MinIO, парсеры
├── presentation/    публичный и внутренний HTTP API
└── settings/        конфигурация backend

alembic/               миграции PostgreSQL
pipeline_contracts/    контракты артефактов и общие enum backend/ML
tests/                 backend unit/integration tests
docker-compose.yml     только PostgreSQL и MinIO
```

## Требования

- Python 3.12;
- `uv`;
- Docker Compose только для PostgreSQL и MinIO.

## Настройка

```bash
cp .env.example .env
uv sync
```

Backend всегда читает корневой `.env`, независимо от текущей директории.
Для связи с `ai_ad_ml` значение `PROCESSING_SERVICE_TOKEN` в обоих репозиториях
должно совпадать.

## Локальный запуск

Поднять инфраструктуру:

```bash
docker compose up -d postgres minio
```

Применить миграции:

```bash
uv run python -m alembic -c alembic.ini upgrade head
```

Запустить backend без Docker:

```bash
uv run python -m uvicorn main:app \
  --app-dir src \
  --host 127.0.0.1 \
  --port 8000 \
  --reload
```

Затем отдельно запускаются:

```bash
cd ../ai_ad_ml
uv run python -m processing_worker.main

cd ../ai_ad_frontend
pnpm dev
```

## Адреса

```text
Backend API:     http://127.0.0.1:8000/api/v1
Internal API:    http://127.0.0.1:8000/internal/v1
Healthcheck:     http://127.0.0.1:8000/healthcheck
OpenAPI:         http://127.0.0.1:8000/docs
PostgreSQL:      127.0.0.1:5432
MinIO API:       http://127.0.0.1:9000
MinIO Console:   http://127.0.0.1:9001
Frontend:        http://127.0.0.1:5173
```

## Обработка видео

1. Frontend создаёт съёмку через `POST /api/v1/runs`.
2. Backend возвращает presigned PUT URL, и браузер загружает видео прямо в
   MinIO.
3. После `POST /runs/{id}/upload-complete` съёмка становится `queued`.
4. ML worker вызывает `POST /internal/v1/processing/jobs/claim`; backend
   атомарно переводит следующую задачу в `processing`.
5. Worker скачивает исходник из MinIO, выполняет пайплайн и отправляет прогресс
   через `/progress`.
6. Worker загружает результаты в `runs/{run_id}/artifacts/` и отправляет
   backend только манифест через `/complete`.
7. Backend проверяет зарегистрированные объекты, сохраняет их метаданные и
   переводит съёмку в `completed`. Ошибка передаётся через `/fail`.
8. Публичные endpoints читают `tracks.csv`, `detections.csv` и `overlay.json`
   из MinIO. Значимость маршрута β и итог `V = S·α·β` рассчитываются только на
   backend.

Внутренние processing endpoints защищены заголовком `X-Processing-Token`.
Текущая версия wire-контракта — `1`; неизвестная версия отклоняется.

## Проверки

Для тестов нужен только PostgreSQL; MinIO подменяется заглушкой:

```bash
docker compose up -d postgres
uv run ruff check pipeline_contracts src tests
uv run mypy pipeline_contracts src tests
uv run pytest
docker compose config --quiet
```

Тестовая база `ad_pipeline_test` создаётся перед набором и удаляется после него.

Проверки соседних репозиториев:

```bash
cd ../ai_ad_ml
uv run ruff check .
uv run mypy ml pipeline_contracts processing_worker tests
uv run pytest

cd ../ai_ad_frontend
pnpm lint
pnpm build
```

## Что не хранится в Git

Локальные `.env`, виртуальные окружения, кеши, видео, ML-веса и результаты
обработки не относятся к backend-репозиторию. Веса находятся локально в
`../ai_ad_ml/models/` и игнорируются его `.gitignore`.
