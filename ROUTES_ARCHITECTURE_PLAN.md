# Централизация загрузок: Город → Маршрут → Пачка → Видео

## Контекст

Проект на стадии pre-mvp. Сейчас в приложении **две почти одинаковые страницы загрузки** — «Новое видео» (`/runs/new`) и загрузка маршрута (`/routes/:cityId/:routeId/upload`). Вторая — copy-paste форк первой. В меню слева они выглядят как два разных продукта, хотя делают одно и то же.

Корень проблемы глубже, чем кнопки. **Бэкенд вообще не знает о городах и маршрутах.** Они захардкожены в `apps/frontend/src/data/cities.ts` и `data/routes.ts`. `RouteUploadPage.tsx` резолвит city/route и использует их **только для заголовка и кнопки «назад»** — `createRun(file)` отправляет на сервер лишь `{file_name, content_type, size_bytes}`. Поля `city_id`/`route_id` не существует ни в API, ни в БД.

Последствия:
- Все видео падают в одну таблицу `pipeline_runs` с одинаковым префиксом `runs/{run_id}/source/` и в один плоский архив `/runs`.
- Видео, загруженное на «Севастопольская | пр. Победы», **неотличимо** от разовой загрузки.
- Связь невосстановима задним числом — её нигде нет. Единственная зацепка — близость по времени.

Целевой результат: одна точка загрузки, у которой **назначение — это параметр, а не отдельная страница**; города и маршруты живут в БД; видео группируются в пачки, и пачка — единица анализа.

## Целевая модель

```
Город (city)  →  Маршрут (route)  →  Пачка (batch)  →  Видео (pipeline_run)
```

Ключевое, из чего следует всё остальное:

- **Метрики считаются на пачку, не на маршрут.** Маршрут — это папка «чтобы понимать, какие видео мы грузим». Пачка = одна съёмка. Отсняли летом → пачка №1 → метрики. Отсняли зимой тот же маршрут → пачка №2 → другие метрики. Пачки копятся на маршруте и никогда не сливаются.
- **Пачка именуется автоматически:** «Пачка №2 · 15.07.2026». Номер сквозной в пределах маршрута. Поля ввода при загрузке нет.
- **Лимит `MAX_BATCH_VIDEOS = 20`** на пачку — константа в коде, не факт схемы. Поднята с 10, чтобы лимит загрузки не резал единицу аналитики пополам (12 видео за съёмку должны остаться одной пачкой). Проверяется на сервере.
- **«Без маршрута»** остаётся: `route_batches_id IS NULL`. Разовые и тестовые загрузки. Именно это делает всю миграцию аддитивной — существующие строки просто становятся «без маршрута», backfill не нужен.

## A. Навигация и URL

Три пункта в рейле + одна кнопка в шапке. **Ни одной загрузки в рейле.**

```
⌂ Продукт     →  /
⚑ Архив       →  /archive     (Города → Маршруты → Пачки → Видео)
▦ Все видео   →  /videos      (плоский список, бейджи + фильтры)

[шапка, справа]  ↑ Загрузить видео  →  /upload
```

Почему так: сейчас в приложении **две параллельные иерархии** — `/routes` (карта, которая упирается в форму загрузки) и `/runs` (плоский архив). Каждая отрастила свою кнопку загрузки. Убрать одну кнопку, не слив иерархии, — значит просто передвинуть путаницу. Поэтому `/routes` и `/runs` сливаются в одно дерево `/archive`; карта не теряется, она становится страницей города внутри дерева. Плоский список остаётся отдельной линзой, потому что решает другую задачу («найти вчерашнее видео» vs «что мы снимали на маршруте X»).

Рейл — это **места**, шапка — **действие**. Загрузка перестаёт быть местом.

| URL | Компонент | Статус |
|---|---|---|
| `/` | `LandingPage` | без изменений |
| `/archive` | `CitiesPage` | карточки городов из API + карточка «Без маршрута» |
| `/archive/:citySlug` | `CityPage` | переименован из `RoutesPage` |
| `/archive/:citySlug/:routeSlug` | `RoutePage` | **новый** — список пачек |
| `/batches/:batchId` | `BatchPage` | **новый** — видео пачки + плейсхолдер метрик |
| `/videos` | `VideosPage` | переименован из `RunsPage`, + фильтры |
| `/videos/:runId` | `RunPage` | внутренности без изменений |
| `/upload`, `/upload?city=X&route=Y` | `UploadPage` | переписан, назначение — параметр |

Удаляются: `/runs/new`, `/routes/:cityId/:routeId/upload`.

«Без маршрута» — карточка в конце сетки городов на `/archive`, ведёт на `/videos?assigned=false`. Отдельная страница не нужна.

Русские подписи: `Загрузить видео` (CTA), `Города и маршруты` (H1 архива), `Открыть маршрут →` (было `Загрузить видео →`), `Пачки маршрута` / `Загрузить пачку`, `Пачка №2 · 15.07.2026`, `7 видео · Готово 5 · В работе 2`, `Метрики по пачке появятся позже`, `В пачку можно загрузить не более 20 видео.`

Редиректы со старых URL не делаем — внешних пользователей нет.

## B. БД

Всё в `apps/backend/src/infrastructure/database/models.py`, в существующем стиле: PK `String(36)` с именем `<table>_id`, `sa_column=Column(...)`, `server_default=func.now()`, `__table_args__` для составных ограничений.

**`cities`** — `cities_id` PK, `slug` String(64) unique idx (`simferopol`), `name`, `region`, `roads_geojson_path` String(512), `display_order`, `is_active`, `created_at`/`updated_at`. `roads_geojson_path` заменяет захардкоженный `export.geojson` в `RoutesPage.tsx:27`.

**`routes`** — `routes_id` PK, `cities_id` FK CASCADE idx, `slug` String(64), `name`, `color_label`, **`color_hex`**, `geojson_path` String(512), `display_order`, `is_active`. `UniqueConstraint(cities_id, slug)`.

> `color_hex` в строке убивает параллельный массив `colors: string[]` из `data/routes.ts:21` — сейчас `colors[i]` связан с `routes[i]` только позицией, и вставка маршрута молча перекрашивает все последующие.

**`route_batches`** — `route_batches_id` PK, `routes_id` FK CASCADE idx, `sequence_number` Integer NOT NULL, `title` String(255) **nullable** (NULL = вычислять), `created_at` idx, `updated_at`. `UniqueConstraint(routes_id, sequence_number)`.

- Колонки `video_count` **нет** — денормализованные счётчики разъезжаются; считаем `GROUP BY` в запросе списка.
- `title` nullable как дешёвый запасной выход: имя `«Пачка №2 · 15.07.2026»` выводится в DTO из `sequence_number` + `created_at`. Когда захочется «Зима 2026» — колонка уже есть.

**Единственная новая колонка в `pipeline_runs`:**

```python
route_batches_id: str | None  # String(36), FK route_batches ondelete="SET NULL", index=True, nullable=True
```

- **`routes_id`/`cities_id` на `pipeline_runs` не денормализуем.** Цепочка run → batch → route → city — два джойна по крошечным таблицам. Денормализация создаёт ровно тот класс бага («правда в двух местах и разъезжается»), ради устранения которого весь рефакторинг.
- `SET NULL`, а не CASCADE: «отвязать видео» обратимо, «уничтожить видео с артефактами» — нет.

**Номер пачки — под блокировкой строки маршрута** (паттерн уже есть в `claim_next()`, `sql_pipeline_run_repository.py:240`):

```python
route = session.exec(select(Route).where(Route.routes_id == route_id).with_for_update()).one_or_none()
next_seq = session.exec(
    select(func.coalesce(func.max(RouteBatch.sequence_number), 0) + 1).where(RouteBatch.routes_id == route_id)
).one()
```

Два одновременных POST сериализуются на строке маршрута → 2 и 3, никогда 2 и 2. `UniqueConstraint` — подстраховка, на `IntegrityError` один ретрай. Postgres `SEQUENCE` **не** использовать — он глобальный, получится «Пачка №1», затем «Пачка №47» на том же маршруте.

### Миграции — не трогаем

**Миграции и сид делает владелец сам, после того как будет готов весь код.** Раздел B — спецификация схемы, а не задание на миграцию.

Полезное для того момента: всё аддитивно и nullable (три таблицы + одна nullable-колонка с FK), поэтому существующие строки просто станут «Без маршрута», backfill не нужен. `6cfc82929998` не переписывать — она уже применена.

**Код готов — осталась схема.** Модели в `models.py` описаны, DDL под Postgres проверен на одноразовой БД. Что нужно завести:

```sql
-- три таблицы (полный DDL генерится из моделей)
CREATE TABLE cities (...);        CREATE UNIQUE INDEX ix_cities_slug ON cities (slug);
CREATE TABLE routes (...);        CREATE INDEX ix_routes_cities_id ON routes (cities_id);
CREATE TABLE route_batches (...); CREATE INDEX ix_route_batches_routes_id ON route_batches (routes_id);
                                  CREATE INDEX ix_route_batches_created_at ON route_batches (created_at);

-- единственная новая колонка
ALTER TABLE pipeline_runs ADD COLUMN route_batches_id VARCHAR(36);
ALTER TABLE pipeline_runs ADD CONSTRAINT fk_pipeline_runs_route_batches_id
  FOREIGN KEY (route_batches_id) REFERENCES route_batches (route_batches_id) ON DELETE SET NULL;
CREATE INDEX ix_pipeline_runs_route_batches_id ON pipeline_runs (route_batches_id);
```

Точный DDL: `alembic revision --autogenerate` увидит модели без доп. импортов (`env.py` уже импортирует `infrastructure.database.models`), но **проверьте `ondelete`** — SQLModel его теряет.

**Сид Симферополя** — 1 город + 4 маршрута, значения точь-в-точь как в удалённом `data/routes.ts`:

| поле | route-1 | route-2 | route-3 | route-4 |
|---|---|---|---|---|
| `name` | Севастопольская \| пр. Победы | Московская \| Киевская | Объездная дорога | Евпаторийское шоссе |
| `color_label` | Красная линия | Синяя линия | Зелёная линия | Жёлтая линия |
| `color_hex` | `#ff3b3f` | `#3b8cff` | `#32c26b` | `#f3c944` |
| `geojson_path` | `routes/simferopol/route_1.geojson` | `..._2.geojson` | `..._3.geojson` | `..._4.geojson` |

Город: `slug='simferopol'`, `name='Симферополь'`, `region='Республика Крым'`, `roads_geojson_path='routes/simferopol/export.geojson'`. **Пути — без ведущего слэша**, фронт добавляет его сам. До сида `GET /api/v1/cities` вернёт пустой список, и `/archive` будет пустым — это ожидаемо.

## C. Storage — не трогаем

**`source_object_key = f"runs/{run_id}/source/{safe_name}"` остаётся как есть** (`pipeline_run_service.py:96`). Раздел C — ноль изменений кода.

Почему не `cities/{city}/routes/{route}/batches/{batch}/...`:

1. **Ключ объекта неизменен, а связь — нет.** Перепривязали видео к другой пачке → ключ стал ложью, либо копируем гигабайты.
2. **`crop_object_key()` (`pipeline_run_service.py:54`) — чистая функция от `run_id`.** Неймспейсинг заставит её ходить в БД, на горячем пути `get_objects()` (вызов на каждый кроп).
3. **Воркер знает только `run_id`** (`pipeline_worker.py:155` пишет `runs/{run_id}/artifacts/{relative}`). Разнести source и artifacts по разным префиксам — хуже, чем сейчас.
4. **UNIQUE ломается.** `safe_file_name()` схлопывает `Видео 1.mp4` и `Видео_1.mp4` в одну строку — два `video.mp4` в одной пачке дадут `IntegrityError`. Пришлось бы всё равно вернуть uuid в ключ.
5. Единственный реальный мотив — «листать MinIO по маршрутам». Это уже решается `SELECT source_object_key ... JOIN`. Если правда понадобится — теги объектов MinIO, они изменяемые.

## D. API

**Новые файлы:** `routers/v1/cities.py`, `routers/v1/batches.py`, `application/services/catalog_service.py`, `application/interfaces/catalog.py`, `infrastructure/repositories/sql_catalog_repository.py`, `application/common/dto/catalog.py`. Проводка: `routers/v1/router.py`, `http/dependencies.py` (`get_catalog_service`), re-export в `__init__.py`.

**Адресация:** города и маршруты по `slug` (курируемые данные со стабильными именами, slug уже в структуре папок geojson), пачки и раны по uuid. Slug маршрута уникален только внутри города → маршруты всегда вложены в город.

```
GET  /api/v1/cities                          → list[CityResponse]        (+ route_count, batch_count, video_count)
GET  /api/v1/cities/{city_slug}              → CityDetailResponse        (routes вложены — CityPage рисует город+маршруты+geojson за один заход)
GET  /api/v1/cities/{c}/routes/{r}/batches   → PaginatedBatchesResponse
POST /api/v1/cities/{c}/routes/{r}/batches   → 201 BatchResponse         (тело пустое — имя автоматическое)
GET  /api/v1/batches/{batch_id}              → BatchResponse
GET  /api/v1/batches/{batch_id}/runs         → list[PipelineRunResponse] (≤20, без пагинации)
```

`BatchResponse { id, sequence_number, title, route{id,slug,name,color_hex}, city{id,slug,name}, video_count, status_counts{...}, created_at }`. Вывод имени — в `CatalogService`, одно место:

```python
def _batch_title(b: RouteBatch) -> str:
    return b.title or f"Пачка №{b.sequence_number} · {b.created_at:%d.%m.%Y}"
```

**Изменения существующих:**

- `CreateRunRequest` (`dto/response.py:40`) + `batch_id: str | None = None`. `create_run(..., batch_id=None)`. Обратно совместимо: без `batch_id` — сегодняшнее поведение, «Без маршрута».
- `GET /runs` + фильтры `city_id`, `route_id`, `batch_id`, `assigned` (uuid, не slug — значения приходят из дропдауна `GET /cities`). Комбинируются через AND.
- `PipelineRunDTO`/`PipelineRunResponse` + `batch: RunBatchRefDTO | None` — питает бейджи на `/videos` за один round trip.

> **Ловушка.** `_run_to_dto()` (`sql_pipeline_run_repository.py:68`) вызывается из `create`, `claim_next`, `mark_completed`, `mark_failed` — **в том числе из воркера**, где связь не загружена. Голый `run.batch` там даст N+1 или упадёт на detached-инстансе. Решение: `_run_to_dto(run, *, with_batch: bool = False)`, и `with_batch=True` только из `list_runs`/`get`, где запрос делает `selectinload(PipelineRun.batch).selectinload(RouteBatch.route).selectinload(Route.city)`. Ровно та же дисциплина, что уже есть для `with_artifacts`/`with_events`.

**Поток загрузки — пачка создаётся один раз, лениво, по кнопке:**

```
1. Пользователь выбрал назначение + бросил файлы   → сети нет вообще
2. «Начать загрузку»:
   a. маршрут?      → POST .../batches → batchId   (ОДИН раз)
      «Без маршрута»? → batchId = null
   b. по каждому файлу последовательно:
        POST /runs { ..., batch_id: batchId }
        PUT  <presigned url>                       (XHR, прогресс)
        POST /runs/{run_id}/upload-complete
3. batchId ? → /batches/{batchId} : (1 ран ? /videos/{runId} : /videos)
```

Не при монтировании страницы — иначе каждый брошенный визит на `/upload?city=..&route=..` оставляет пустую «Пачку №5». Не неявно на первом файле — иначе `POST /runs` получает вторую работу, а проверка лимита — особую ветку «пачка только что создана».

**Лимит — на сервере, авторитетно**, в `create_run`, в существующей транзакции:

```python
MAX_BATCH_VIDEOS = 20   # константа рядом с ALLOWED_VIDEO_EXTENSIONS

if batch_id is not None:
    self._repository.lock_batch(batch_id)              # SELECT ... FOR UPDATE
    if self._repository.count_batch_runs(batch_id) >= MAX_BATCH_VIDEOS:
        raise BatchFullError(f"В пачку можно загрузить не более {MAX_BATCH_VIDEOS} видео.")
```

`FOR UPDATE` на строке пачки сериализует параллельные `POST /runs` — без него два запроса, каждый насчитав 19, оба вставят и получится 21. На клиенте `maxFiles: 20` — только UX. В БД бэкстопа нет: межтабличное «count ≤ 20» без триггера не выразить, а триггер того не стоит.

Новые исключения в `application/exceptions.py` + хендлеры: `CatalogNotFoundError(LookupError)` → 404 (город/маршрут/пачка одним классом), `BatchFullError(ValueError)` → 409.

**Частичный сбой пачки — нормальное состояние, транзакции нет.** 7 из 10 прошло → пачка существует с 7 видео, `Загружено 7 из 10`, кнопка «Повторить» шлёт только упавшие **в тот же `batchId`** (хук держит его в state). Это и есть выигрыш «пачка сначала»: иначе ретрай родил бы фантомную «Пачку №3» из трёх отставших.

> **Существующий баг, который станет заметным.** Если `POST /runs` прошёл, а presigned PUT упал — строка навсегда виснет в `UPLOADING` без объекта. Это уже так сегодня, но в плоском архиве незаметно. Внутри пачки с лимитом висяки едят слоты (считать их обязательно — иначе мусор копится безнаказанно). Лечение: `DELETE /api/v1/runs/{run_id}` (только при `status == UPLOADING`), хук зовёт его при падении PUT. Фаза 3 или осознанно отложить.

## E. Фронтенд

**Общая абстракция — хук, не компонент.** Создать `apps/frontend/src/hooks/` (первый хук в проекте — сейчас каждая страница инлайнит свои `useState`/`useEffect`).

`src/hooks/useVideoUpload.ts` возвращает `{ items, busy, dragActive, limitNotice, batchId, addFiles, removeItem, clearAll, start, retryFailed, dragHandlers }`, опции `{ maxFiles, createBatch?: () => Promise<string|null>, onFinish? }`.

Хук забирает всё, что сегодня дублируется: дедуп по `${name}-${size}-${lastModified}`, кламп `maxFiles` + `limitNotice`, drag-состояние, последовательный цикл `createRun → uploadVideo → completeUpload`, попроцентный прогресс, одноразовое создание пачки, ретрай упавших в ту же пачку.

Именно **хук**, потому что дублируется **поведение** (машина состояний загрузки), а расходятся страницы **представлением**. Общий компонент пришлось бы обвешивать пропами под каждое различие — так форк и родился.

**Одиночная загрузка — это `maxFiles: 1`.** Двух UI не держим; список из одной строки рисуется тем же кодом, а `navigate('/runs/{id}')` из `UploadPage.tsx:33` становится веткой в `onFinish`.

Побочно чинится: у `RouteUploadPage` **нет** `onDragLeave` и `dragActive` (ср. `UploadPage.tsx:56-72`) — зона сброса никогда не гаснет. `dragHandlers` даёт обеим страницам правильную версию.

**Форк `FileCard`.** `RouteUploadPage.tsx:161-182` рисует `.file-card` руками, потому что общий компонент не принимает детей. Расширить настоящий: `FileCard({ file, status?: ReactNode, actions?: ReactNode, children?: ReactNode })` — иконка + имя + `formatBytes`, затем `children` (прогресс/ошибка), затем `status`/`actions`. Инлайновый форк удалить.

**Прочее:**
- `InfoBanner` в `components/common/Feedback.tsx` — `RouteUploadPage.tsx:156` рисует нотис «максимум 10 файлов» через `ErrorBanner`, то есть валидацию в стилях ошибки.
- **Извлечь `components/common/RunCard.tsx`** из `RunsPage.tsx:62-83`, пропсы `{ run, showBadges? }`. Нужен и `VideosPage`, и `BatchPage`. Извлечь **сразу** — именно это не даёт родиться следующему близнецу.

**Страницы:** `RouteUploadPage.tsx` — **удалить**; `UploadPage.tsx` — переписать (пропсы `{citySlug?, routeSlug?}`, селектор назначения, хук); `RoutesPage.tsx` → `CityPage.tsx`; `RunsPage.tsx` → `VideosPage.tsx` (+ фильтры, бейджи); **новые** `RoutePage.tsx`, `BatchPage.tsx`; `CitiesPage.tsx` — на API + карточка «Без маршрута»; `RunPage.tsx` — хлебная крошка к `run.batch`; `ResultPage/ProcessingPage/LandingPage` — только цели `navigate()`. **Удалить** `data/cities.ts`, `data/routes.ts`.

**Замена статики на API при статичном geojson.** Типы `City/Route/CityDetail/RouteBatch/RunBatchRef` → в `src/types.ts`. `findCity()`/`findRoute()` удалить — резолвит и 404-ит сервер, в этом весь смысл переезда в БД.

Сейчас `RoutesPage.tsx:26-28` склеивает пути сам. После — **в БД лежит полный относительный путь, фронт не склеивает ничего**:

```ts
fetch(`/${city.roads_geojson_path}`)      // 'routes/simferopol/export.geojson'
...routes.map((r) => fetch(`/${r.geojson_path}`))
```

Конвенция: путь **без ведущего слэша и без домена**, относительно `apps/frontend/public/`; фронт добавляет `/`. Файлы остаются ровно там, где лежат. Добавление города = seed-миграция + папка `public/routes/<slug>/`. Конвенцию записать комментарием на колонке. Цвета: `routes.map(r => r.color_hex)` вместо `cityData.colors` — сигнатура пропа `RouteMap` не меняется. `routeCount: 4` из `cities.ts` → `city.route_count` (сейчас это число поддерживается руками и разъедется при первом же добавлении маршрута).

**`src/api.ts`:** новые `getCities`, `getCity`, `getRouteBatches`, `createBatch`, `getBatch`, `getBatchRuns`. Изменённые: `createRun(file, batchId?)`, `listRuns(params?: {page?, status?, cityId?, routeId?, batchId?, assigned?})` — строку запроса собирать `URLSearchParams`, пропуская undefined. `apiFetch` и распаковка `{data:T}` не трогаются.

**`src/routing.ts`:** `Route` = `home | archive | city{citySlug} | route{citySlug,routeSlug} | batch{batchId} | videos{filters} | upload{citySlug?,routeSlug?} | run{runId}`. `currentRoute()` теперь читает `window.location.search` через `URLSearchParams` для `/upload` и `/videos` (~6 строк). `navigate()` не меняется — он и так пушит полный путь. Заодно: финальный `return { page: 'runs' }` — **молчаливый catch-all**, любой опечатанный URL рисует архив; направить в `archive` или завести `not-found`.

## F. Страница пачки

**Видео в пачке — независимые проезды маршрута.** Проехали → запись, проехали снова → ещё запись. N проездов = одна пачка. GPS/телеметрии в записях **нет и не планируется**.

### Принцип: слой над страницей видео, а не семь страниц видео

`ResultPage` не трогаем — она хорошая. Страница пачки это агрегат + навигация вниз; клик по проезду уводит на знакомую страницу видео. Семь блоков графиков на одной странице не кладём: это стена, которую никто не читает, и она стирает единственное, ради чего пачка есть — общий ответ.

### Что агрегируется

- **Метрики.** «Объектов» — сумма. «Индекс заметности» — среднее, **взвешенное по длительности** (20-секундный огрызок не должен весить как 10-минутный проезд). Плюс то, чего на видео нет: `7 проездов`, `суммарно 48 минут`, `обработано 5 из 7`.
- **Графики по брендам (pie + bar).** Складываются честно — им ось времени не нужна. Суммируем `object_count` по брендам со всех готовых видео. Самая ценная часть страницы, достаётся почти даром: `RunCharts` переиспользуется без таймлайна.
- **Топ объектов.** Топ-12 по всей пачке — «самая заметная реклама на маршруте». Меняется смысл клика: сейчас `setSeek` перематывает плеер на той же странице, здесь плеера нет → переход на `/videos/{runId}?t=12.3`. Нужен параметр `?t=` в URL и проброс в `seekRequest` `VideoOverlayPlayer`. На кропе — подпись, из какого проезда.
- **Считаем на лету** при открытии страницы: бэкенд читает `BRAND_SUMMARY` готовых видео пачки и складывает. Кэш-таблицы `batch_summaries` **нет** — нет рассинхрона, метрики сами обновляются по мере обработки, на 10 видео это миллисекунды.

### Чего на странице пачки нет

**Плеера нет** — семь видео одновременно не играются, выбирать «главное» бессмысленно.

**Таймлайна нет.** Проезды независимы, поэтому:
- склейка врёт про непрерывность (каждое видео начинается с начала маршрута);
- наложение по времени врёт про сопоставимость — ось «секунды» несопоставима между проездами: один щит на свободной дороге будет на 0:30, а в пробке на 2:10, и кривые разъезжаются тем сильнее, чем дальше от старта.

Оба варианта врут → таймлайн остаётся только на странице видео, где он честный (одно видео, реальное время, клик перематывает плеер).

**Тепловой заливки маршрута не будет никогда.** Честная ось для вопроса «где на маршруте заметно» — не время, а положение на маршруте, то есть заливка линии geojson на карте. Она требует привязки кадра к координате, а GPS нет и не планируется. Отсюда следствие, которое надо принять: **маршрут никогда не станет аналитической осью, он навсегда ярлык.** Карта на странице города — навигация и иллюстрация. Единственная связь видео с маршрутом — выбор оператора при загрузке; больше её взять неоткуда.

### Что заменяет таймлайн: сравнение проездов

Список проездов с цифрами — он же и есть сравнение. Не сетка превью: у дашкам-видео все превью одинаковые (дорога), отличить нечем. Полезнее строки:

```
● Пачка №2 · 15.07.2026
  Симферополь · Севастопольская | пр. Победы
  7 проездов · 48 мин · обработано 5 из 7

  [ метрики: Объектов | Индекс | Проездов | Длительность ]
  [ графики по брендам: pie + bar ]
  [ топ объектов по пачке → /videos/{id}?t= ]

Проезды                                  [ Добавить видео ]
  ▶ pass1.mp4   ✓  8:12   142 объекта   индекс 0.61   →
  ▶ pass2.mp4   ✓  9:04   201 объект    индекс 0.74   →
  ▶ pass3.mp4   ⟳  Детекция · 64%                     →
  ▶ pass4.mp4   ✕  Ошибка кодека                      →
```

Видно, какой проезд вытягивает индекс, а какой пустой — список работает и как навигация, и как таблица сравнения. `●` — цвет маршрута из `color_hex`, тот же, что линия на карте.

Опционально (чуть больше работы): bar-график «индекс по проездам» — показывает разброс между проездами. Честный, в отличие от таймлайна.

## Фазы

Порядок работы, а не порядок релизов: миграции в конце, поэтому вживую ничего не проверить, пока владелец не заведёт схему.

**Фаза 0 — только модели.** `models.py`: `City`, `Route`, `RouteBatch`, `PipelineRun.route_batches_id`.

**Фаза 1 — каталог на чтение + переезд фронта.** DTO/репозиторий/сервис/роутер каталога, `GET /cities`, `GET /cities/{slug}`; фронт — `CitiesPage` и `RoutesPage` на API, **удаление `data/cities.ts` и `data/routes.ts`**, geojson-пути и цвета из БД. UI пиксель-в-пиксель тот же, данные серверные. Проверяет seed и конвенцию путей **до** того, как на них лягут пачки. Лучшее соотношение ценность/риск.

**Фаза 2a — пачки и консолидация загрузки (ядро).** `create_batch` (блокировка строки + аллокация номера), эндпоинты пачек, `create_run(batch_id=...)` + `MAX_BATCH_VIDEOS` + блокировка + `BatchFullError` → 409; `useVideoUpload`, переписанный `UploadPage`, **удаление `RouteUploadPage`**, расширенный `FileCard`, `InfoBanner`.

**Фаза 2b — навигация.** Новый `Route`-юнион + парсинг query, рейл на 3 пункта + CTA в шапке (~12 мест с `navigate()`), `RoutePage`, `BatchPage`, переименования `RoutesPage`→`CityPage`, `RunsPage`→`VideosPage`. После 2 близнец мёртв, пачки копятся.

**Фаза 3 — фильтры и бейджи.** Фильтры `GET /runs`, `PipelineRunDTO.batch` + `_run_to_dto(with_batch=...)` + `selectinload`-цепочка; фильтр-бар и бейджи на `VideosPage`, извлечение `RunCard`, карточка «Без маршрута». Сюда же — `DELETE /runs/{run_id}` для висяков.

**Фаза 4 — метрики пачки** (раздел F). `GET /batches/{id}/summary` — агрегат на лету по `BRAND_SUMMARY` готовых видео; метрики + графики по брендам + топ объектов на `BatchPage` вместо заглушки; `?t=` в URL страницы видео. Схема к этому моменту уже готова — всё катится по `route_batches_id`, новых таблиц не нужно.

**Осознанно отложено:** переименование пачки (`PATCH /batches/{id}`, колонка уже есть); пагинация списка пачек; админка городов/маршрутов (сид — правильный инструмент для 8-15 курируемых городов, CMS не строим); кэш geojson на клиенте (сейчас `export.geojson` ~580 КБ перекачивается на каждый визит города); редиректы со старых URL.

## Рабочий процесс

- **Миграции не трогаем** — владелец делает их сам, после готовности всего кода.
- **Не коммитим** — ветки, коммиты, PR на владельце.

## Риск, который надо держать в голове

**Две линзы на архив (`/archive` и `/videos`) — это ровно та форма, что породила текущее дублирование** (`/routes` vs `/runs`). Требование законное, но защита должна быть структурной: `RunCard` извлечён и общий с первого дня, обе линзы зовут **один** `GET /runs` с разными параметрами. Если у плоского списка заведётся своя вёрстка карточки или свой эндпоинт — мы вернулись в начало.

## Верификация

Всё ниже — **после того, как владелец заведёт схему и сид**. До этого момента код проверяется только типами и тестами.

1. **Схема заведена:** `SELECT count(*) FROM pipeline_runs WHERE route_batches_id IS NULL` равен полному числу существующих ранов (старые видео стали «Без маршрута»), старый UI работает без изменений.
2. **Фаза 1:** `curl /api/v1/cities` и `/api/v1/cities/simferopol` → 4 маршрута с `color_hex` и `geojson_path`. Открыть `/archive/simferopol` — карта и цвета линий **идентичны** тому, что было на статике (сравнить скриншотом до/после). `/api/v1/cities/nonexistent` → 404.
3. **Фаза 2:** поднять фронт, бэк, воркер, MinIO. Загрузить 3 файла на маршрут → в БД одна строка `route_batches` с `sequence_number=1` и три рана с её `route_batches_id`; UI показывает «Пачка №1 · <дата>». Повторить на том же маршруте → `sequence_number=2`, первая пачка на месте. Загрузить через «Без маршрута» → `route_batches_id IS NULL`, в `/archive` не появляется.
4. **Лимит:** попытаться залить 21 файл → фронт не даёт выбрать 21-й; отдельно `curl` 21 раз `POST /runs` с одним `batch_id` → 409 с русским текстом. Гонка: два параллельных `POST .../batches` на один маршрут (`xargs -P2`) → номера 1 и 2, не 1 и 1.
5. **Воркер не сломан:** после загрузки в пачку ран доходит до `COMPLETED`, артефакты на месте, `/videos/{runId}` рисует результат. Это проверяет ловушку `_run_to_dto(with_batch=...)` — воркер не должен ловить detached-инстанс.
6. **Частичный сбой:** остановить MinIO на середине пачки → упавшие items в ошибке, «Повторить» дозаливает **в ту же пачку** (`sequence_number` не вырос, новой строки в `route_batches` нет).
