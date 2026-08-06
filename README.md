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
Dockerfile             образ FastAPI и одноразовых миграций
docker-compose.yml     backend, миграции, PostgreSQL и MinIO
```

## Требования

- Docker с Compose — для контейнерного запуска;
- Python 3.12 и `uv` — для запуска и разработки без Docker.

## Настройка

```bash
cp .env.example .env
uv sync
```

Backend всегда читает корневой `.env`, независимо от текущей директории.
Для связи с `ai_ad_ml` значение `PROCESSING_SERVICE_TOKEN` в обоих репозиториях
должно совпадать.

## Запуск в Docker

Compose собирает backend, поднимает PostgreSQL и MinIO, применяет миграции
одноразовым сервисом `migrate` и только после этого запускает API:

```bash
docker compose up -d --build
```

Проверить состояние и логи:

```bash
docker compose ps
docker compose logs -f backend
```

Локальный `.env` передаётся контейнерам, но внутренние адреса PostgreSQL и
MinIO Compose заменяет на имена сервисов. `MINIO_PUBLIC_ENDPOINT` остаётся
адресом, доступным браузеру; по умолчанию это `http://127.0.0.1:9000`.

Frontend и ML worker имеют собственные compose-файлы и запускаются из соседних
репозиториев после backend:

```bash
cd ../ai_ad_frontend
docker compose up -d --build

cd ../ai_ad_ml
docker compose up -d --build
```

Для ML-контейнера нужны NVIDIA Container Toolkit, доступная GPU и локальные
веса в `../ai_ad_ml/models/`. Значения `PROCESSING_SERVICE_TOKEN` и реквизиты
MinIO в `.env` backend и ML должны совпадать.

Остановка каждого сервиса выполняется в его репозитории:

```bash
docker compose down
```

Тома PostgreSQL и MinIO при обычном `down` сохраняются.

## Запуск без Docker

Для разработки приложение по-прежнему можно запускать нативно. Сначала
поднимите только инфраструктуру и примените миграции:

```bash
docker compose up -d postgres minio
uv run python -m alembic -c alembic.ini upgrade head
```

Затем запустите backend:

```bash
uv run python -m uvicorn main:app \
  --app-dir src \
  --host 127.0.0.1 \
  --port 8000 \
  --reload
```

Frontend и worker запускаются отдельно:

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
