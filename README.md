# AI Ad Pipeline

Сервис для анализа видео с наружной рекламой. Пользователь загружает ролик, backend кладет исходник в MinIO, worker забирает задачу из PostgreSQL, запускает ML-пайплайн и сохраняет результаты обратно в MinIO. Frontend читает summary, objects, timeline, overlay и playback через HTTP API.

Проект сейчас удобнее запускать в dev-режиме: PostgreSQL, MinIO и backend живут в Docker, worker запускается локально из `.venv`. Так проще работать с моделями, GPU и файлами в репозитории.

## Что внутри

```text
apps/backend/          FastAPI, Alembic, SQLModel, MinIO storage, worker
apps/frontend/         React + Vite интерфейс
ml/pipeline/           локальный ML-пайплайн для видео
pipeline_contracts/    общие enum и Pydantic-контракты backend/ML
models/                веса моделей: detection и classification
outputs/               локальные результаты standalone-запусков
```

Временной папки worker-а на хосте нет: он работает в контейнере и пишет в том `worker_runtime`.

Важный момент: `pipeline_contracts` используют и backend, и ML-код. В `docker-compose.yml` эта папка примонтирована в контейнеры `backend` и `migrate`:

```yaml
- ./pipeline_contracts:/app/pipeline_contracts:ro
```

Без этого Alembic внутри контейнера падает с `ModuleNotFoundError: No module named 'pipeline_contracts'`.

## Требования

- Docker + Docker Compose
- `nvidia-container-toolkit` на хосте — без него worker не стартует
- модели:
  - `models/detection/best.pt`
  - `models/classification/best.pt`

Python `3.12`, `uv`, Node.js и `pnpm` нужны только для тестов и линтеров: сам стенд целиком живет в контейнерах.

## Видеокарта в контейнере

### Зачем нужен тулкит

CUDA состоит из двух половин, и в контейнер ставится только одна.

**Пользовательская часть** — `libcudart`, cuBLAS, cuDNN, NCCL. Обычные библиотеки, приезжают колесами `nvidia-*` вместе с `torch` при сборке образа. Ставить отдельно ничего не надо, они уже там.

**Драйвер** — `libcuda.so.1` и модуль ядра. Ядро у контейнера общее с хостом, своего нет, поэтому драйвер туда не устанавливается в принципе. Его пробрасывает снаружи `nvidia-container-toolkit` — хук OCI, который при старте контейнера монтирует внутрь библиотеки драйвера и узел устройства.

Отсюда две ошибки, которые выглядят по-разному:

| Симптом | Что это значит |
|---|---|
| `no known GPU vendor found`, контейнер вообще не стартует | тулкита нет или демон не перечитал конфиг |
| контейнер работает, `torch.cuda.is_available()` → `False` | устройство не проброшено, либо в образ поставили CUDA Toolkit через apt и подцепилась заглушка `libcuda.so` из `stubs/` |

Вторая ошибка коварнее: собирается все прекрасно, а видеокарты нет. **Не ставьте CUDA Toolkit в образ** — это лечение не той половины.

### Установка (Debian / Ubuntu, в том числе внутри WSL)

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

Список пакетов у NVIDIA один на все deb-дистрибутивы, версию Ubuntu подставлять не нужно. Если в системе нет systemd — вместо последней строки `sudo service docker restart`.

Перезапуск демона поднимет заново все контейнеры с политикой `restart: unless-stopped` — в том числе чужих проектов. Посмотреть, кого это заденет, до перезапуска:

```bash
docker ps --format '{{.Names}}'
```

Что делают две последние команды:

- `nvidia-ctk runtime configure` дописывает рантайм `nvidia` в `/etc/docker/daemon.json`;
- перезапуск демона заставляет Docker перечитать этот файл.

### Проверка

Не тяните ради этого образ `nvidia/cuda` — своего достаточно:

```bash
docker run --rm --gpus all ai-ad-pipeline-worker:dev \
  python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

Ожидаемый ответ — `True` и название карты.

### Нужно ли переставлять после обновления ядра

**Нет.** Тулкит целиком в пространстве пользователя: бинарник хука и спецификация CDI, модуля ядра у него нет. Обновление ядра ему безразлично.

Обновление ядра может задеть **драйвер NVIDIA** — это другой пакет. На обычном Linux модуль `nvidia.ko` пересобирается под новое ядро; штатный пакет `nvidia-driver-*` делает это сам через DKMS. Под WSL модуля нет вообще: карта приходит через `/dev/dxg`, а `libcuda.so.1` в `/usr/lib/wsl/lib` подкладывает сам WSL из драйвера Windows при каждом старте.

Освежать после обновления ядра надо **спецификацию CDI** — файл `/var/run/cdi/nvidia.yaml`, по которому Docker понимает, что за GPU в системе. Он лежит в tmpfs и перезагрузку не переживает. Но делать руками ничего не нужно: пакет ставит два юнита systemd, оба включены:

```
nvidia-cdi-refresh.service   выполняет nvidia-ctk cdi generate
nvidia-cdi-refresh.path      следит за /lib/modules/<ядро>/modules.dep и /usr/bin/nvidia-ctk
```

`.path` срабатывает ровно на смену модулей ядра и на обновление самого тулкита, `.service` дополнительно поднимается при загрузке. Условие запуска написано с оглядкой на WSL: годится либо `nvidia.ko` в `modules.dep`, либо просто наличие `/dev/dxg`.

Проверить, что автоматика на месте:

```bash
systemctl is-enabled nvidia-cdi-refresh.path nvidia-cdi-refresh.service
ls -l /var/run/cdi/nvidia.yaml
```

### Когда все-таки придется вмешаться

| Событие | Что делать |
|---|---|
| Переустановка или крупное обновление Docker, сбросившее `daemon.json` | `sudo nvidia-ctk runtime configure --runtime=docker` и перезапуск демона |
| Обновление драйвера NVIDIA в Windows (WSL) | на стороне Linux ничего; полезно перезапустить WSL — `wsl --shutdown` из PowerShell |
| `/var/run/cdi/nvidia.yaml` пропал, а юниты выключены | `sudo nvidia-ctk cdi generate --output=/var/run/cdi/nvidia.yaml` |
| Обновление ядра | ничего |

### Без видеокарты

Обработка возможна, но медленная и годится только чтобы убедиться, что цепочка работает: поставьте `PIPELINE_DEVICE=cpu` в `apps/backend/.env` и уберите `gpus: all` у сервиса `worker` в `docker-compose.yml`.

## Переменные окружения

Backend читает `apps/backend/.env`. Если файла нет:

```bash
cp apps/backend/.env.example apps/backend/.env
```

Основные значения:

```env
POSTGRES_DB=ad_pipeline
POSTGRES_USER=ad_pipeline
POSTGRES_PASSWORD=change_me
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432

MINIO_ROOT_USER=ad_pipeline
MINIO_ROOT_PASSWORD=change_me
MINIO_BUCKET=ad-pipeline
MINIO_INTERNAL_ENDPOINT=http://127.0.0.1:9000
MINIO_PUBLIC_ENDPOINT=http://127.0.0.1:9000

PIPELINE_DETECTOR_MODEL_PATH=models/detection/best.pt
PIPELINE_CLASSIFIER_MODEL_PATH=models/classification/best.pt
PIPELINE_BRAND_OVERRIDES_PATH=ml/pipeline/brand_overrides.csv
PIPELINE_FRAME_STRIDE=1
PIPELINE_DEVICE=0
PIPELINE_WORKER_TEMP_DIR=.runtime/worker
```

В Docker Compose backend получает другие адреса для внутренних сервисов:

```yaml
POSTGRES_HOST: postgres
MINIO_INTERNAL_ENDPOINT: http://minio:9000
MINIO_PUBLIC_ENDPOINT: http://127.0.0.1:9000
PYTHONPATH: /app/apps/backend/src:/app
```

`MINIO_PUBLIC_ENDPOINT` специально остается `127.0.0.1`, потому что presigned URL возвращается браузеру.

Worker получает то же самое плюс свои две переменные:

```yaml
PIPELINE_WORKER_TEMP_DIR: /app/.runtime/worker
YOLO_CONFIG_DIR: /tmp
```

Первая перекрывает относительный путь из `.env` — он должен совпасть с точкой монтирования тома `worker_runtime`. Вторая нужна ultralytics: свой `settings.json` он кладет в конфиг пользователя, которого в контейнере нет. Подкаталог `Ultralytics` библиотека дописывает сама, поэтому значение — родитель, а не полный путь.

## Быстрый запуск всего стенда

Весь стенд поднимается одной командой:

```bash
docker compose up
```

Она делает все по порядку:

- поднимает `postgres` и `minio` и ждет их готовности;
- прогоняет Alembic-миграции одноразовым сервисом `migrate`;
- запускает backend на `http://127.0.0.1:8000`;
- запускает worker с доступом к видеокарте;
- запускает frontend на `http://127.0.0.1:5173`.

Backend и worker ждут именно успешного завершения `migrate`, поэтому отдельно применять миграции не нужно.

Первая сборка образа worker-а долгая: в него ставится `torch` с CUDA-колесами, это порядка 6 ГБ. Дальше образ кешируется и пересобирается только при изменении `uv.lock`.

Остановить стенд:

```bash
docker compose down
```

Логи одного сервиса:

```bash
docker compose logs -f worker
```

Пересобрать образ, если менялись `pyproject.toml`, `uv.lock` или `Dockerfile`:

```bash
docker compose build backend
docker compose build worker
docker compose build frontend
```

Локальное Python-окружение нужно только для тестов и линтеров, стенду оно не требуется:

```bash
uv sync
```

Полная очистка контейнеров и данных этого проекта:

```bash
docker compose down --volumes --remove-orphans
```

Перед удалением можно проверить, что Docker видит именно этот compose-проект:

```bash
docker compose ps -a
docker volume ls --filter label=com.docker.compose.project=ai_ad_pipeline_apps
```

Ожидаемые volumes:

```text
ai_ad_pipeline_apps_frontend_node_modules
ai_ad_pipeline_apps_minio_data
ai_ad_pipeline_apps_postgres_data
ai_ad_pipeline_apps_worker_runtime
```

## Адреса

```text
Backend API:     http://127.0.0.1:8000
Healthcheck:     http://127.0.0.1:8000/healthcheck
OpenAPI docs:    http://127.0.0.1:8000/docs
MinIO API:       http://127.0.0.1:9000
MinIO Console:   http://127.0.0.1:9001
Frontend dev:    http://127.0.0.1:5173
```

## Frontend

Frontend лежит отдельно в `apps/frontend` и поднимается вместе со всем остальным — это сервис `frontend` в compose, Vite в режиме разработки на `5173`. Собранная статика намеренно не используется: адрес API подставляется в сборку, и прод-образ пришлось бы пересобирать при каждой его смене.

Адрес API задается переменной сервиса в `docker-compose.yml`:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1
```

Зависимости стоят в образе, поверх исходников смонтирован том `frontend_node_modules`. Том наполняется из образа один раз, при создании, поэтому после правки `package.json` пересборки образа мало — том надо снести:

```bash
docker compose build frontend
docker compose down frontend
docker volume rm ai_ad_pipeline_apps_frontend_node_modules
docker compose up -d frontend
```

Если пропустить снос тома, в контейнере останутся старые зависимости, а образ будет свежий — расхождение тихое.

Запускать `pnpm` локально нужно только для линтера и проверки сборки:

```bash
cd apps/frontend
pnpm install
pnpm lint && pnpm build
```

## Как проходит обработка видео

API работает через presigned upload.

1. Frontend создает run:

   ```http
   POST /api/v1/runs
   ```

   В теле передаются `file_name`, `content_type`, `size_bytes`.

2. Backend создает запись в PostgreSQL со статусом `uploading` и возвращает presigned `PUT` URL в MinIO.

3. Frontend загружает файл напрямую в MinIO.

4. Frontend сообщает backend-у, что загрузка завершена:

   ```http
   POST /api/v1/runs/{run_id}/upload-complete
   ```

5. Backend проверяет объект в MinIO, регистрирует source artifact и переводит run в `queued`.

6. Worker забирает задачу, скачивает исходное видео в `/app/.runtime/worker/<run_id>/input` внутри контейнера, запускает ML-пайплайн и пишет результаты в `/app/.runtime/worker/<run_id>/output`. Это том `worker_runtime`, каталог прогона удаляется после работы — и после успеха, и после ошибки.

7. Worker загружает артефакты в MinIO, регистрирует их в БД и переводит run в `completed`.

После обработки временная папка worker-а удаляется.

## Основные API endpoints

Все ручки живут под `/api/v1`.

```text
POST /runs
POST /runs/{run_id}/upload-complete
GET  /runs
GET  /runs/{run_id}
GET  /runs/{run_id}/status
GET  /runs/{run_id}/summary
GET  /runs/{run_id}/objects?limit=100
GET  /runs/{run_id}/timeline?bucket_seconds=10
GET  /runs/{run_id}/overlay
GET  /runs/{run_id}/playback
GET  /runs/{run_id}/artifacts
GET  /runs/{run_id}/artifacts/{artifact_id}/url
```

`status` в `GET /runs` типизирован через enum `PipelineRunStatus`. Примеры значений:

```text
uploading
queued
processing
completed
processing_failed
```

Progress stage тоже enum. Значения лежат в `pipeline_contracts/pipeline.py`: `upload`, `queued`, `preparing`, `detection`, `tracking`, `classification`, `aggregation`, `rendering`, `uploading_artifacts`, `completed`, `failed`.

## Standalone-запуск ML-пайплайна

Если нужно прогнать ML без backend-а и очереди:

```bash
./run_video_pipeline.sh path/to/video.mp4
```

Без аргумента скрипт берет:

```text
ml/data/pipeline/input/VideoProject.mp4
```

Настройки можно переопределять через env:

```bash
FRAME_STRIDE=1 DEVICE=cpu ./run_video_pipeline.sh path/to/video.mp4
```

Полная команда под капотом:

```bash
.venv/bin/python -m ml.pipeline.run_pipeline \
  --input path/to/video.mp4 \
  --detector-model models/detection/best.pt \
  --classifier-model models/classification/best.pt \
  --frame-stride 1 \
  --device 0
```

Результаты standalone-запуска попадают в:

```text
outputs/pipeline/<run_id>/
```

Обычно там есть:

```text
input_meta.json
detections.csv
tracks.csv
brand_summary_by_tracks.csv
brand_summary_by_detections.csv
frame_summary.csv
overlay.json
viewer.html
report.html
crops/
charts/
```

В backend-режиме worker загружает почти все это в MinIO. Crops физически загружаются, но не регистрируются отдельными DB artifacts: они используются для `crop_url` в `/objects`.

## Контракты и DTO

Общие контракты лежат в `pipeline_contracts`.

```text
pipeline_contracts/pipeline.py   статусы run, stages, artifact types
pipeline_contracts/domain.py     enum-ы доменной логики ML
pipeline_contracts/artifacts.py  Pydantic-модели CSV/JSON артефактов
```

Backend не должен держать вторую копию этих схем. ML writer пишет CSV через Pydantic-модели, backend читает эти же форматы и валидирует ответы через DTO.

Есть важная деталь с CSV. В `tracks.csv` пустой `final_brand` означает пустую строку, а не `null`. Поэтому backend читает CSV так:

```python
pd.read_csv(io.BytesIO(value), keep_default_na=False)
```

Если убрать `keep_default_na=False`, `pandas` превратит пустые строки в `NaN`, потом JSON-сериализация даст `null`, и `/objects` может упасть на Pydantic-валидации.

## Договоренности по backend-коду

- `__init__.py` не содержит бизнес-логику. Только re-export.
- Application service работает через protocol-интерфейсы, а не напрямую с SQLAlchemy, MinIO или Docker.
- Storage-интерфейсы разделены:
  - `RunObjectStorage` нужен API-слою: presigned URL, stat, read bytes/text.
  - `WorkerObjectStorage` нужен worker-у: ensure bucket, download, upload.
- Статусы, стадии и типы артефактов идут через enum, без строковых литералов в бизнес-логике.
- SQL repository мапит SQLModel-модели в application DTO.
- Commit/rollback остаются на границах use case: service или worker явно завершает транзакцию.
- Response DTO в presentation не должны заново копировать поля application DTO без причины.

## Docker-нюансы

Source backend-а и Alembic монтируются в контейнер read-only:

```yaml
- ./apps/backend/src:/app/apps/backend/src:ro
- ./apps/backend/alembic:/app/apps/backend/alembic:ro
- ./apps/backend/alembic.ini:/app/apps/backend/alembic.ini:ro
```

`pipeline_contracts` тоже монтируется read-only. Это позволяет менять Python-код и контракты без пересборки image.

Worker монтирует то же самое плюс `./ml` и `./models`. Веса в образ не кладутся: они весят 350 МБ и лежат вне git. Рабочий каталог прогона — том `worker_runtime`, а не слой контейнера: через overlayfs гигабайты видео ходят медленно.

Image все равно нужно пересобрать, если изменились зависимости или Dockerfile:

```bash
docker compose build backend
```

Если контейнеры запутались или хочется начать с чистой БД и пустого MinIO:

```bash
docker compose down --volumes --remove-orphans
docker compose up
```

Эта команда удаляет данные только текущего compose-проекта. Для проверки используй label:

```bash
docker volume ls --filter label=com.docker.compose.project=ai_ad_pipeline_apps
```

## Проверки перед коммитом

Python:

```bash
uv run ruff check pipeline_contracts apps/backend/src ml/pipeline/scripts ml/pipeline/run_pipeline.py
uv run mypy pipeline_contracts apps/backend/src ml/pipeline/scripts ml/pipeline/run_pipeline.py
```

Frontend:

```bash
cd apps/frontend
pnpm lint
pnpm build
```

Проверка compose-файла:

```bash
docker compose config
```

Быстрая проверка backend-а:

```bash
curl http://127.0.0.1:8000/healthcheck
```

Ожидаемый ответ:

```json
{"status":"ok"}
```

## Типичные проблемы

### `ModuleNotFoundError: No module named 'pipeline_contracts'`

Контейнер не видит общий пакет контрактов. Проверь, что в `docker-compose.yml` есть mount:

```yaml
- ./pipeline_contracts:/app/pipeline_contracts:ro
```

И что `PYTHONPATH` содержит `/app`:

```yaml
PYTHONPATH: /app/apps/backend/src:/app
```

После правки можно проверить миграции отдельно:

```bash
docker compose run --rm migrate
```

### `/objects` возвращает 500

Смотри traceback backend-а:

```bash
docker compose logs --tail=200 backend
```

Если ошибка похожа на `final_brand Input should be a valid string`, значит CSV прочитан с превращением пустых строк в `NaN/null`. В `_read_csv` должен быть `keep_default_na=False`.

### Worker ничего не обрабатывает

Смотри логи: `docker compose logs -f worker`. Проверь, что:

- контейнер `ai-ad-worker` запущен и не перезапускается по кругу;
- run перешел в `queued`;
- MinIO доступен на `9000`;
- модели лежат в `models/detection/best.pt` и `models/classification/best.pt`;
- в `.env` правильный `PIPELINE_DEVICE`.

Отдельный случай: контейнер поднялся и пишет `worker started`, а обработка падает на первом же видео. CUDA трогается не при старте, а когда загружаются модели, поэтому worker без видеокарты выглядит здоровым ровно до первой съемки. Проверь тулкит: `docker run --rm --gpus all nvidia/cuda:12.6.0-base-ubuntu24.04 nvidia-smi`.

### Backend поднялся, но frontend не видит API

Проверь `apps/frontend/.env`:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1
```

Backend CORS по умолчанию разрешает:

```text
http://localhost:5173
http://127.0.0.1:5173
```

### Нужно понять, какой контейнер относится к проекту

Compose ставит label:

```text
com.docker.compose.project=ai_ad_pipeline_apps
```

Проверка:

```bash
docker ps -a --filter label=com.docker.compose.project=ai_ad_pipeline_apps
```

## Что считать успешным прогоном

В логах worker-а нормальный финал выглядит так:

```text
processed sampled frames: ...
detections after gate: ...
objects: ...
tracks: ...
viewer: .../viewer.html
report: .../report.html
run completed: <run_id>
```

После этого должны отвечать:

```text
GET /api/v1/runs/{run_id}/summary
GET /api/v1/runs/{run_id}/objects?limit=100
GET /api/v1/runs/{run_id}/timeline?bucket_seconds=10
GET /api/v1/runs/{run_id}/overlay
GET /api/v1/runs/{run_id}/playback
```

Если `summary`, `overlay`, `timeline` отвечают `200`, а `/objects` падает, проблема почти наверняка не в ML-прогоне, а в API-чтении `tracks.csv`.
