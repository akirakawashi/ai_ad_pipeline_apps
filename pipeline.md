# Web-система обработки видео

## 1. Цель

Нужно построить приложение, в котором пользователь:

1. Загружает видео.
2. Видит прогресс загрузки и ML-обработки.
3. После завершения открывает отдельную страницу результата.
4. Просматривает видео с интерактивным overlay.
5. Анализирует объекты, кадры, метрики и графики.
6. Может вернуться к любому ранее обработанному видео.

Каждая загрузка создаёт независимый `pipeline run`. История не удаляется и не
перезаписывается.

```text
upload
  -> queued
  -> detection / crop quality
  -> tracking / object grouping
  -> classification
  -> aggregation / business rules
  -> rendering / artifact upload
  -> completed
```

## 2. Основные архитектурные решения

### 2.1. Компоненты

```text
React frontend
    |
    v
FastAPI backend ---- PostgreSQL
    |
    +-------------- MinIO
    |
    v
Pipeline worker ---- GPU / ML models
```

- Frontend отвечает за загрузку, отображение статуса, player, overlay и
  интерактивные графики.
- FastAPI создаёт runs, выдаёт upload URL, читает историю и предоставляет API
  результатов.
- PostgreSQL хранит состояние runs, прогресс, ошибки и ссылки на артефакты.
- MinIO хранит исходные видео и результаты pipeline.
- Worker запускается отдельным процессом, забирает задачи из PostgreSQL и
  выполняет ML pipeline.

Backend и worker используют одну кодовую базу, но запускаются разными
процессами. ML pipeline нельзя выполнять внутри HTTP-запроса или
`BackgroundTasks`: обработка долгая, использует GPU и не должна зависеть от
перезапуска web-сервера.

### 2.2. Очередь без Redis

Для первой версии отдельный Redis/Celery не нужен. PostgreSQL используется и
как хранилище состояния, и как простая надёжная очередь.

Worker выбирает одну задачу:

```sql
SELECT pipeline_runs_id
FROM pipeline_runs
WHERE status = 'queued'
ORDER BY created_at
FOR UPDATE SKIP LOCKED
LIMIT 1;
```

После захвата worker переводит run в `processing` и фиксирует `worker_id` и
`started_at`. Такой подход позволяет позже запустить несколько workers без
двойной обработки одного run.

## 3. Docker Compose

В корне проекта находится `docker-compose.yml` с:

- PostgreSQL на `localhost:5432`;
- MinIO API на `localhost:9000`;
- MinIO Console на `localhost:9001`.

Используются явно зафиксированные image tags:

```text
postgres:18.4-trixie
minio/minio:RELEASE.2025-09-07T16-13-09Z
```

Оба контейнера получают переменные из `apps/backend/.env`. При запуске
backend должен проверять наличие bucket `ad-pipeline` и создавать его, если он
ещё не существует.

Значения по умолчанию:

```text
POSTGRES_DB=ad_pipeline
POSTGRES_USER=ad_pipeline
POSTGRES_PASSWORD=ad_pipeline

MINIO_ROOT_USER=ad_pipeline
MINIO_ROOT_PASSWORD=ad_pipeline_secret
MINIO_BUCKET=ad-pipeline
```

Для корпоративного стенда значения должны передаваться через переменные
окружения. В репозитории не нужно хранить реальные пароли.

## 4. Модель данных PostgreSQL

### 4.1. `pipeline_runs`

Одна строка — одна загрузка и одна независимая обработка.

```text
pipeline_runs_id            UUID, primary key
source_name                 исходное имя файла
source_object_key           ключ исходного видео в MinIO
source_content_type
source_size_bytes

status                      created/uploading/queued/processing/completed/
                            upload_failed/processing_failed
stage                       upload/detection/tracking/classification/...
progress                    integer 0-100
status_message
error_code
error_message

fps
frame_count
frame_stride
duration_sec
width
height

created_at
upload_completed_at
started_at
completed_at
updated_at
worker_id
```

Удаление через API в первой версии не реализуется. Повторная загрузка того же
файла создаёт новый `run_id`.

### 4.2. `pipeline_artifacts`

```text
pipeline_artifacts_id       UUID, primary key
pipeline_runs_id            FK -> pipeline_runs.pipeline_runs_id
artifact_type
object_key
content_type
size_bytes
created_at
```

Примеры `artifact_type`:

```text
source_video
annotated_video
overlay
detections
tracks
brand_summary
frame_summary
crop
report
```

### 4.3. `pipeline_run_events`

Необязательная, но полезная таблица для истории обработки:

```text
pipeline_run_events_id      UUID, primary key
pipeline_runs_id            FK -> pipeline_runs.pipeline_runs_id
stage
progress
message
created_at
```

Она позволит показать пользователю журнал этапов и понять, где упал pipeline.

## 5. Структура объектов MinIO

Используется один bucket, внутри которого каждый run имеет свой prefix:

```text
runs/{run_id}/source/original.mp4

runs/{run_id}/artifacts/input_meta.json
runs/{run_id}/artifacts/overlay.json
runs/{run_id}/artifacts/detections.csv
runs/{run_id}/artifacts/tracks.csv
runs/{run_id}/artifacts/brand_summary_by_tracks.csv
runs/{run_id}/artifacts/frame_summary.csv
runs/{run_id}/artifacts/report.html
runs/{run_id}/artifacts/video/annotated_video.mp4
runs/{run_id}/artifacts/crops/...
```

Локальная директория worker является временной:

```text
/tmp/ad-pipeline/{run_id}/input/
/tmp/ad-pipeline/{run_id}/output/
```

После загрузки всех артефактов в MinIO её можно очистить. Источником истины
остаются PostgreSQL и MinIO.

## 6. Загрузка видео

### 6.1. Рекомендуемый вариант: presigned PUT

```text
Frontend
  -> POST /api/v1/runs
Backend
  -> создаёт run со status=uploading
  -> возвращает run_id и presigned upload URL
Frontend
  -> PUT video directly to MinIO
Frontend
  -> POST /api/v1/runs/{run_id}/upload-complete
Backend
  -> проверяет объект
  -> status=queued
```

Преимущества:

- большой файл не проходит через FastAPI;
- backend не держит длинное соединение;
- можно показывать реальный upload progress;
- credentials MinIO не попадают во frontend.

Важно: URL MinIO в presigned ссылке должен быть доступен из браузера. Адрес
`http://minio:9000` доступен контейнерам, но не браузеру. Нужны две настройки:

```text
MINIO_INTERNAL_ENDPOINT=http://minio:9000
MINIO_PUBLIC_ENDPOINT=http://localhost:9000
```

Для корпоративного стенда public endpoint будет внутренним DNS-именем.

Если frontend и MinIO находятся на разных origins, для bucket/API необходимо
настроить CORS. Альтернативный вариант — проксировать MinIO через тот же
внутренний reverse proxy и домен, что и frontend/backend.

### 6.2. Альтернатива: загрузка через backend

```text
POST /api/v1/runs/upload
Content-Type: multipart/form-data
```

Backend потоково передаёт файл в MinIO. Это проще с точки зрения сети и CORS,
но backend становится промежуточным каналом для всего видео.

Для MVP предпочтителен presigned PUT. Backend upload можно оставить как
fallback.

### 6.3. Прогресс загрузки

Прогресс загрузки известен frontend локально:

```text
uploaded_bytes / file.size
```

Для presigned PUT следует использовать `XMLHttpRequest`, потому что он
предоставляет `xhr.upload.onprogress`. Этот процент не нужно постоянно писать
в PostgreSQL.

## 7. Состояния run

```text
created
  -> uploading
  -> queued
  -> processing
  -> completed
```

Ошибочные состояния:

```text
upload_failed
processing_failed
```

Этапы внутри `processing`:

```text
preparing
detection
tracking
classification
aggregation
rendering
uploading_artifacts
```

Пример распределения общего процента:

```text
preparing              0-2
detection              2-65
tracking               65-70
classification         70-82
aggregation            82-87
rendering              87-96
uploading_artifacts    96-99
completed              100
```

Для detection процент рассчитывается по:

```text
processed_sampled_frames / ceil(frame_count / frame_stride)
```

Rendering выполняет второй проход по исходному видео, поэтому ему также нужен
собственный progress callback.

## 8. Изменения ML pipeline

Вычислительную логику менять не требуется. Нужен внешний callback прогресса:

```python
class PipelineProgressReporter(Protocol):
    def update(
        self,
        stage: str,
        progress: int,
        message: str | None = None,
    ) -> None: ...
```

CLI использует reporter, который пишет в logger. Worker использует reporter,
который обновляет PostgreSQL.

Порядок стадий сохраняется:

```text
detection / crops / quality
-> tracking
-> object grouping
-> classification
-> final aggregation
-> overrides
-> business stabilization
-> annotated video
-> overlay and reports
```

Worker:

1. Захватывает queued run.
2. Скачивает source video из MinIO.
3. Создаёт локальный `PipelineConfig`.
4. Запускает pipeline с progress reporter.
5. Загружает output directory в prefix run.
6. Записывает artifacts в PostgreSQL.
7. Переводит run в `completed`.
8. При исключении сохраняет traceback и переводит run в
   `processing_failed`.

## 9. Backend API

### Загрузка и состояние

```text
POST   /api/v1/runs
POST   /api/v1/runs/{run_id}/upload-complete
GET    /api/v1/runs/{run_id}/status
```

`POST /runs` принимает:

```json
{
  "file_name": "route-01.mp4",
  "content_type": "video/mp4",
  "size_bytes": 123456789
}
```

И возвращает:

```json
{
  "run_id": "uuid",
  "status": "uploading",
  "upload": {
    "method": "PUT",
    "url": "presigned-url",
    "headers": {
      "Content-Type": "video/mp4"
    }
  }
}
```

### История и результаты

```text
GET /api/v1/runs?page=1&page_size=20&status=completed
GET /api/v1/runs/{run_id}
GET /api/v1/runs/{run_id}/summary
GET /api/v1/runs/{run_id}/objects
GET /api/v1/runs/{run_id}/timeline
GET /api/v1/runs/{run_id}/overlay
GET /api/v1/runs/{run_id}/artifacts
GET /api/v1/runs/{run_id}/artifacts/{artifact_id}/url
```

Существующие read endpoints можно сохранить. Их repository нужно заменить с
локального `FilePipelineRunRepository` на PostgreSQL + MinIO.

Для первой версии frontend опрашивает status endpoint каждые 1-2 секунды.
После стабилизации можно добавить SSE:

```text
GET /api/v1/runs/{run_id}/events
```

WebSocket здесь не обязателен: клиенту нужен преимущественно однонаправленный
поток статуса.

## 10. Frontend

### 10.1. Страницы

```text
/runs             история обработок
/runs/new         загрузка нового видео
/runs/{run_id}    статус или результат конкретного run
```

### 10.2. Экран загрузки

- drag-and-drop;
- проверка типа и размера файла;
- имя и размер видео;
- progress bar загрузки;
- возможность повторить upload после ошибки;
- после завершения upload автоматический переход на страницу run.

### 10.3. Экран обработки

- название видео;
- общий progress;
- текущий этап;
- список уже завершённых этапов;
- время старта и прошедшее время;
- понятное состояние ошибки;
- polling статуса до `completed` или `processing_failed`.

Обновление страницы не должно сбрасывать состояние: frontend восстанавливает
его через `GET /runs/{run_id}`.

### 10.4. Экран результата

```text
VideoPlayerWithOverlay
SummaryCards
BrandDistributionChart
VisibilityShareChart
VisibilityTimelineChart
TopObjectsChart
ObjectGallery
RunMetadata
```

Клик по точке timeline или объекту:

1. Устанавливает `video.currentTime`.
2. Прокручивает список к соответствующему object.
3. Подсвечивает bbox и карточку.

Клик по crop переводит видео на `best_timestamp_sec`.

### 10.5. История

Карточка run содержит:

- thumbnail или первый значимый crop;
- исходное имя файла;
- статус;
- дату загрузки;
- длительность;
- число объектов;
- основные бренды;
- время обработки.

История загружается с серверной пагинацией. Удаление отсутствует.

## 11. Интерактивные графики

Во frontend используется Recharts 3:

```bash
pnpm add recharts react-is
```

Причины выбора:

- библиотека уже использовалась в другом frontend проекта;
- `ResponsiveContainer`, line, area, bar, pie и scatter;
- `Brush` для выбора части timeline;
- собственные tooltip и legend;
- обработчики клика, которыми можно управлять `video.currentTime`;
- простая композиция React-компонентов без отдельной imperative API.

Набор графиков первой версии:

1. `Objects by brand` — bar chart.
2. `Visibility share` — donut chart.
3. `Visibility timeline` — stacked area/line по времени и брендам.
4. `Top visible objects` — horizontal bar.
5. `Confidence vs visibility` — scatter для диагностики качества.

Backend должен отдавать данные, а не готовые PNG. PNG/HTML charts,
генерируемые текущим pipeline, можно сохранить как диагностические артефакты,
но основной UI рисует графики в браузере.

## 12. Video player и overlay

Не следует встраивать текущий `viewer.html` через iframe как основную
реализацию frontend.

Нужно переиспользовать формат `overlay.json` и перенести rendering overlay в
React:

```text
HTMLVideoElement
  + absolute overlay layer
  + bbox components
  + object cards
```

Текущий frame определяется так:

```text
frame_index = round(video.currentTime * fps)
```

Для плавности обновление выполняется через `requestAnimationFrame`. Overlay
масштабирует координаты bbox относительно фактического размера video element.

Должны поддерживаться два режима:

- исходное видео + интерактивный overlay;
- готовое `annotated_video.mp4` как простой fallback/download.

## 13. Этапы реализации

### Этап 1. Инфраструктура

- PostgreSQL и MinIO из `docker-compose.yml`;
- настройки backend;
- SQLAlchemy/asyncpg и Alembic;
- MinIO client;
- миграции `pipeline_runs`, `pipeline_artifacts`, `pipeline_run_events`.

### Этап 2. Upload

- создание run;
- presigned PUT;
- upload-complete;
- проверка объекта;
- status `queued`;
- frontend upload screen.

### Этап 3. Worker

- PostgreSQL job claiming;
- скачивание source;
- progress reporter;
- запуск pipeline;
- загрузка artifacts;
- обработка ошибок.

### Этап 4. История и status UI

- список runs;
- пагинация;
- polling;
- processing screen;
- восстановление состояния после reload.

### Этап 5. Result page

- player;
- React overlay;
- summary;
- object gallery;
- Recharts;
- синхронизация графиков и player.

### Этап 6. Эксплуатационные улучшения

- retry failed run;
- heartbeat и возврат зависших jobs в очередь;
- ограничение числа параллельных GPU jobs;
- multipart upload больших файлов;
- SSE;
- retention policy, если хранение станет слишком дорогим.

## 14. Критерии готовности MVP

- пользователь загружает видео из браузера;
- upload progress отображается;
- после upload создаётся queued job;
- worker выполняет pipeline отдельно от FastAPI;
- progress обработки отображается после reload страницы;
- результаты лежат в MinIO;
- metadata и история лежат в PostgreSQL;
- каждый run имеет отдельную страницу;
- старые runs доступны из истории;
- player показывает bbox поверх видео;
- графики интерактивны и синхронизируются с видео;
- ошибка pipeline видна пользователю и не удаляет историю run.
