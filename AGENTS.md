# AGENTS.md — working context for AI agents

Read this file first. It is the map; the code is the territory. Companion document:
[docs/pipeline-and-metrics.md](docs/pipeline-and-metrics.md) — the same system described in Russian
for the human owner, with all formulas spelled out. **Both files must stay true after every change
you make** (see §11).

Language note: this file is English on purpose (dense, matches identifiers). The codebase itself has
**Russian comments and Russian user-facing strings** — keep writing them that way.

---

## 1. What this project is

Outdoor-advertising visibility measurement from dashcam video. A car drives a route, the video is
uploaded, a CV pipeline finds billboards, identifies the brand, and computes **how well each
billboard was seen**. Results are shown per shooting, per assignment and per route.

Three target brands: `mts`, `plus7`, `miranda`. Everything else collapses to `other`.

---

## 2. Hard rules

1. **Never commit, never push. The owner does that.** Leave your work in the working tree and say
   what you changed — no `git commit`, no `git push`, no branches, no stashing, no reverting someone
   else's work. Same for database migrations: generate the file if asked, but the owner applies it.
   Do not ask for permission to commit either; just stop at "changed, not committed".
2. **Clean slate, no compatibility layers.** When something is replaced, the old thing is deleted in
   the same change — no dual fields, no feature flags, no "legacy" slots, no deprecation windows.
   This is an explicit standing instruction from the owner.
3. **The pipeline computes physics only.** ML side produces `attention_seconds` (S) and
   `confidence_coef` (α). The significance coefficient β and the final value `V = S·α·β` are
   computed **on the backend at request time** from route geozones. Never write β or V into pipeline
   artifacts, never bake β into the CSV contract. Rationale: zones are drawn *after* processing and
   change at will — there is no moment at which β is final.
4. **Artifact/DTO shapes live in `pipeline_contracts/`.** This repository owns the backend's copy;
   the standalone ML repository has a matching copy in `../ai_ad_ml/pipeline_contracts/`. A contract
   change is one coordinated change in both repositories and must keep the processing wire contract
   at version `1` until an explicit version migration is designed. `src/domain/entities/`
   is a thin re-export facade — do not add logic there.
5. **Tunable numbers go into config dataclasses**, never into `if` branches:
   [`../ai_ad_ml/ml/pipeline/scripts/config.py`](../ai_ad_ml/ml/pipeline/scripts/config.py)
   (`ScoringConfig` and friends).
   Business tunes tables without touching code.
6. **Do not run the full pipeline unless asked.** It needs a GPU, model weights
   (`../ai_ad_ml/models/*/best.pt`, gitignored) and a real video. Prefer unit tests.
7. **`docs/refactoring-backlog.md` is a backlog, not a task list.** Do not act on it unless the
   owner explicitly asks.
8. **The ad catalogue must not touch the visibility metric.** `ad_structures` is a directory of
   billboards standing in a city; the pipeline's `object_id` is a per-video cluster of detections.
   Different things — see the naming trap in §10. Wiring catalogue coefficients into β is a separate,
   unstarted step.

---

## 3. Repo map

| Path | What lives there |
|---|---|
| `pipeline_contracts/` | Backend copy of the artifact contracts: CSV row models, overlay payload, enums (`PipelineRunStatus`, `PipelineRunStage`, `PipelineArtifactType`, `FinalStatus`, …), brand constants. Must match the ML copy. |
| `../ai_ad_ml/ml/pipeline/` | Standalone ML pipeline: CLI, orchestration, scoring, reports and overlay generation. It does not import this repository. |
| `../ai_ad_ml/processing_worker/` | Standalone worker. Claims jobs and reports progress/results through backend HTTP; reads/writes objects in MinIO; never connects to PostgreSQL. |
| `src/domain/` | Pure logic, no I/O: `auth.py` (`Permission`, claim parsing, group→permission whitelist), `geozones.py` (`beta`, `overlaps`), `catalog.py` (point collapsing, revision diff, city bounds), `geometry.py` (geojson validation, bbox, route line assembly), `route_snapping.py` (road graph + map matching: a hand-drawn stroke onto real roads) + entity facades. |
| `src/application/` | Services (`pipeline_run_service`, `catalog_service`, `metrics_rollup`, `user_service`), DTOs, repository interfaces. |
| `src/infrastructure/` | SQLModel models, SQL repositories, MinIO storage, `catalog/parser.py` (xlsx/xls/csv), `auth/keycloak.py` (code exchange + JWKS signature verification). |
| `src/presentation/http/` | FastAPI routers, request/response DTOs, DI, exception handlers, `auth.py` (session cookie, `current_user`, `require_admin`, `allow_hidden`). |
| `src/application/services/processing_job_service.py` | Backend side of the processing boundary: atomically claims queued work, accepts progress and validates/registers completed artifacts. |
| `src/presentation/http/routers/internal/` | Token-protected processing API under `/internal/v1`; contract version is `1`. |
| `alembic/` | Migrations. Exactly two since the 28.07.2026 squash: `0001_schema` (all eleven tables, including the append-only `dwh_video_metrics`) and `0002_seed` (two cities **with their road layers**, seven routes **without lines** — tests depend on these). `seed_data/geometry/<city>/export.geojson` holds the two road layers the seed reads; they are migration assets, not leftovers — delete them and a from-scratch database comes up with an empty map. Route lines are drawn in the admin panel, not seeded (31.07.2026, see §10); the seven `route_N.geojson` that used to live here are now reference fixtures in `tests/fixtures/routes/`. While there is no production database the chain is squashed rather than extended; the day real data exists, that stops and history is append-only. |
| `../ai_ad_frontend/src/` | React 19 + Vite + Recharts in the companion repository. Hand-rolled router (`routing.ts`), no react-router. |
| `tests/` | pytest. Needs a live Postgres; MinIO is faked. |
| `docs/refactoring-backlog.md` | The only planning document left. `docs/plan.md` and its per-step files existed until 28.07.2026 and are gone: intent that has landed belongs in `pipeline-and-metrics.md`, not in a parallel history. Do not recreate them. |
| `README.md` | Setup and local-run guide for the separated repositories. |

---

## 4. Runtime topology

The three repositories are packaged independently. Each owns its `Dockerfile` and
`docker-compose.yml`; no Compose file reaches into a neighbouring source tree. Start backend first,
then frontend and ML from their repositories. Native commands remain the faster development path.

| Piece | How it runs | Where |
|---|---|---|
| Postgres | backend Compose | `:5432`, persistent named volume |
| MinIO | backend Compose | `:9000` API, `:9001` console, persistent named volume |
| Migrations | backend Compose one-shot `migrate` service | backend waits for successful completion |
| Backend (FastAPI) | backend Compose or native uvicorn | `:8000`, public prefix `/api/v1`, internal prefix `/internal/v1`, health at `/healthcheck` |
| Worker + ML | ML Compose with `gpus: all` or native Python | temporary files under `PIPELINE_WORKER_TEMP_DIR`; GPU selected by `PIPELINE_DEVICE` |
| Frontend | frontend Compose (local Vite preview) or native Vite | `127.0.0.1:5173` (in backend CORS allowlist) |

Backend config comes from the repository-root `.env` (gitignored), resolved independently of the current
working directory. ML/worker config comes from `../ai_ad_ml/.env`. Both must carry the same
`PROCESSING_SERVICE_TOKEN` (at least 16 characters). The worker's API client deliberately ignores
host `HTTP_PROXY`/`HTTPS_PROXY`: backend is a local trusted service and inherited proxy settings can
turn a healthy localhost request into a proxy-generated 503. PostgreSQL credentials exist only in
backend; the ML repository has no database dependency or setting. In containers, backend uses the
Compose service names `postgres` and `minio`; the ML Compose reaches the published backend/MinIO
ports through `host.docker.internal`, including the Linux `host-gateway` mapping. Frontend's
`VITE_API_BASE_URL` is a build argument because Vite embeds it into the generated static bundle.

---

## 5. The metric — canonical definition

```
per detection (frame k):   I_k = A_k · P_k · C_k
per object:                S   = Σ_k ( I_k · Δt_k )        "attention seconds"
per object, backend only:  V   = S · α · β
```

* `A` area, `P` position + side of road, `C` contrast to background — each in 0…1, from
  interpolated tier tables in `ScoringConfig`. Multiplied, not summed: one weak factor must sink the
  moment.
* `Δt = sample_delta_t_sec = frame_stride / fps`. **Time is the integration axis, never a separate
  multiplier** — multiplying by duration again would double-count it.
* `α = confidence_coef ∈ [0.5, 1.0]` from `final_brand_conf`. Floor 0.5: the billboard was seen even
  if the brand is uncertain.
* `β = significance` from route geozones, by **time fraction** of the video, computed on the backend.
  Neutral 1.0 outside marked zones.

Field placement:

| Where | Fields |
|---|---|
| `DetectionRecord` / `detections.csv` | `area_coef`, `position_coef`, `contrast_coef`, `intensity` |
| `TrackRecord` / `tracks.csv` | `attention_seconds` (S), `confidence_coef` (α) |
| Backend, computed live | `significance_coef` (β), `visibility_value` (V) |

⚠ **Name collision to keep straight:** in `../ai_ad_ml` the label `visibility_value` means **S·α**
(derived in its `reporting/writer.py` and `viewer/payload.py` for standalone reports and overlay
cards).
On the backend `visibility_value` means **S·α·β**. They are different numbers with the same name.

---

## 6. End-to-end flow

0. An assignment is created in the admin panel («Задания» tab, city-scoped) — it is the campaign a
   shooting is uploaded into. Everything below is open to everyone; this step is not.
1. `POST /api/v1/runs` → row in `pipeline_runs` (status `uploading`) + presigned PUT URL.
   **`assignment_id` is mandatory** — a shooting always belongs to an assignment and through it to a
   route; the assignment row is locked (a hidden one is refused as "not found") and capped at
   `MAX_ASSIGNMENT_SHOOTINGS = 20`. **`shot_started_at` is mandatory too** — it is the route chart
   and date-filter axis; the frontend pre-fills it from file metadata but both the API and the
   `NOT NULL` database column refuse an undated shooting.
2. Browser PUTs the file straight to MinIO: `runs/{run_id}/source/{safe_name}`.
3. `POST /runs/{run_id}/upload-complete` → registers the `source_video` artifact, status `queued`.
   The one read that still answers for a hidden assignment: the file is already stored.
4. ML worker calls `POST /internal/v1/processing/jobs/claim` with `X-Processing-Token` and contract
   version `1`. The backend performs `SELECT … FOR UPDATE SKIP LOCKED`, commits status `processing`,
   and returns the source object's bucket/key. The worker downloads it from MinIO and reports stages
   with `POST .../{run_id}/progress`; only backend writes `pipeline_runs` and
   `pipeline_run_events`. The second table is **write-only** — see §10.
5. Pipeline stages: detection → tracking → classification → final aggregation → business rules →
   artifacts.
6. Worker uploads everything under `runs/{run_id}/artifacts/…`, then posts the artifact manifest and
   video metadata to `POST .../{run_id}/complete`. The backend rejects escaping/duplicate paths,
   verifies every declared object in MinIO, derives artifact types itself, registers them and marks
   the run completed in one transaction. Crops are uploaded but **not** put in the manifest
   (`should_register_artifact`). Completion stores fps / frame_count / frame_stride / width / height
   and **`duration_sec = frame_count / fps`** — β depends on this value. After duration is stored,
   the backend reuses the same live summary calculation as the product API and appends one
   `dwh_video_metrics` row per brand (`sum_visibility_value = Σ(S·α·β)`) with revision `1`; a result
   without brands gets one row with both `brand` and the value NULL. Artifact registration, the
   `completed` status and DWH publication commit as one transaction. Failure is reported through
   `POST .../{run_id}/fail`. There is no lease/heartbeat yet: a process death between claim and
   failure reporting leaves a run in `processing`, as the old in-process worker did.
7. Reads: `GET /runs/{id}/summary` and `/objects` parse **`tracks.csv`** from MinIO and apply β on
   the fly; `/timeline` parses `detections.csv`; `/overlay` returns `overlay.json`. `pipeline_runs`
   has exactly six read endpoints — `/{id}`, `/summary`, `/objects`, `/timeline`, `/overlay`,
   `/playback` — and `api.ts` calls all six. Keep it that way; the three that nobody called were
   deleted on 30.07.2026 (see §10).
8. Rollup calls `get_summary` per completed shooting → **mean and median, plus std** across
   shootings, all three in one response (`MetricStat`); the UI toggle picks which centre to show.
   Two entry points, one code path: `/assignments/{id}/summary` (shootings of one assignment) and
   `/cities/{c}/routes/{r}/summary` (all shootings of the route). **The route averages shootings
   directly — there is no mean-of-means step**, so a two-drive campaign cannot outweigh a
   twenty-drive one; the route response also carries every shooting with its assignment. Two things
   can shorten the route's list before the rollup — the date period and a hidden assignment — and
   neither changes how it computes (see §10).
9. Route/city geometry lives in the DB (`routes.geometry`, `cities.roads_geometry`) and is served by
   `/cities/{c}/roads-geometry` and `/cities/{c}/routes/{r}/geometry` with weak `ETag`s. **The two
   sides arrive differently, and that is the point:** a city's road layer is uploaded as a geojson
   file (`PUT /cities/{c}/roads-geometry`, recomputes the bounds in the same operation), while a
   route's line is **drawn by hand over that layer** (`POST /cities/{c}/routes/{r}/geometry`, body
   `{"stroke": [[lon, lat], …]}`). The stroke is snapped onto the real road network by
   `domain/route_snapping.py`; uploading a route geojson is gone (30.07.2026, see §10). **The seed
   follows that split:** `0002_seed` reads the two `export.geojson` road layers and computes each
   city's bounds from them, so an empty database comes up with a working map — but it seeds no route
   lines at all, because a line is something you draw (31.07.2026, see §10). Consequence to expect on
   a fresh database: roads are there, every route says «линии нет», and
   `GET /cities/{c}/routes/{r}/geometry` answers 404 until someone draws it.
10. Frontend renders charts from `/summary`, `/objects`, `/timeline`, and the player from
   `/overlay` + `/playback`.

---

## 7. Change cookbook

| I need to… | Touch |
|---|---|
| Retune area/position/contrast/confidence numbers | `ScoringConfig` in `../ai_ad_ml/ml/pipeline/scripts/config.py` only |
| Change how a factor is computed | the one file in `../ai_ad_ml/ml/pipeline/scripts/scoring/`, plus its class in `../ai_ad_ml/tests/test_scoring.py` |
| Add/remove a CSV column | update `pipeline_contracts/artifacts.py` in **both** repositories → the dataclass in `../ai_ad_ml/ml/pipeline/scripts/schemas.py` → every reader; run both repositories' contract/tests before handoff |
| Change β semantics / zone model | `src/domain/geozones.py` + `_apply_beta` in `pipeline_run_service.py` + `RouteGeozone` model |
| Change how zones are entered or edited | `../ai_ad_frontend/src/components/RouteGeozones.tsx` — one panel for both mounts (city page without video, shooting card with it); percent↔fraction lives in `toFraction`/`percentText` there |
| Add an endpoint | router in `presentation/http/routers/v1/` → response DTO in `presentation/http/dto/response.py` → service → repository interface → SQL repository. It is behind the session automatically (the v1 router applies `current_user` to everything); add `Depends(require_admin)` if it administers rather than operates |
| Add a DB table/column | `infrastructure/database/models.py`, then the schema change goes **into `0001_schema`**, not into a third migration — there is still no production database (see §3). Generate it only when asked; **the owner applies it**, and the owner must wipe the volume for an edited `0001_schema` to take effect. Verify with `alembic check` against a scratch database: `pytest` proves the code runs on the migrated schema but not that the migration matches the models |
| Change how an assignment **or a route** aggregates shootings | `application/services/metrics_rollup.py` — the only place that decides how shootings collapse (today: mean + median + std), shared by both levels. Which shootings reach it is decided earlier, in `list_route_runs`; do not move that decision here or the other way round |
| Change how an assignment is created, edited or hidden | `components/AdminAssignments.tsx` (the only mount of `AssignmentForm.tsx` — route picker, create, edit, hide/show) → `createAssignment` / `updateAssignment` / `getRouteAssignments` in `api.ts` → `assignments.py` + `cities.py` routers (both writes behind `require_admin`) → `catalog_service` → `sql_catalog_repository`. `RoutePage.tsx` and `AssignmentPage.tsx` only display; do not put a form back into either |
| Change what a hidden assignment hides | `is_active` threads through **nine** reads. Seven in `sql_catalog_repository.py`: `list_assignments`, `get_assignment`, `_assignment_counts_by_route`, `_video_counts_by_route`, the two city-level counters in `list_cities`, and `list_route_runs` (this is the metric). Three in `sql_pipeline_run_repository.py`: `list_runs`, `get`, and `lock_assignment` — the last one guards the upload and **must stay in that file**, next to its only caller; see the twin trap in §10. Miss one and you get half-hidden: a card gone from the list but its video still counted |
| Change the route's date period | `list_route_runs` in `sql_catalog_repository.py` (the `[shot_from, shot_to)` window) → `get_route_summary` in `catalog_service.py` → `cities.py` router → `getRouteSummary` in `api.ts` → `PeriodPicker` in `RouteSummaryPanel.tsx`, with the window itself in the URL (`routePath`). Date↔instant conversion lives in `utils/formatters.ts`. **The filter stays on the server** — see §10 |
| Change which centre estimate the UI shows, or add a third one | `MetricStatDTO` → `_stat()` in `metrics_rollup.py` → `MetricStat` in `types.ts` → `statValue`/`formatStat` in `utils/formatters.ts` → `AggregateToggle.tsx`, which is mounted only by `MetricsPanel.tsx` (the summary tiles and the toggle are one card; among the tiles it changes only «объектов за видео», while brand visibility changes in the charts below). The choice itself never reaches the backend, and it is held by the **page** (`RoutePage` / `AssignmentPage`), not by the panel — the panel unmounts on a tab switch and the selection has to survive that |
| Change what the route/assignment page shows, or add a tab | `PageView` in `routing.ts` (`?view=analytics`, absent means work) → `routePath` / `assignmentPath` → `VIEW_TABS` in `RoutePage.tsx` / `AssignmentPage.tsx`. **The rollup request is gated on the tab** — that is what makes it lazy; do not hoist it out of that condition. `App.tsx` deliberately keeps the tab out of the page `key` so switching does not remount and refetch |
| Add a city/route field, change geometry handling | `domain/geometry.py` (validation only) → `models.py` → `sql_catalog_repository` → `catalog_service` → `cities.py` router → `AdminPage.tsx`. Geometry must stay out of list responses |
| Change how a route's line is drawn or snapped | `domain/route_snapping.py` — graph building, candidate search, Viterbi, stitching, and `SnappingConfig`. Quality is measured, not eyeballed: [tests/test_route_snapping.py](tests/test_route_snapping.py) traces all seven real routes. Read the two traps in §10 before touching the graph or the tests |
| Change the drawing surface (zoom, pan, the stroke itself) | `RouteMap.tsx` (`zoomable` / `drawing` / `onSegmentDrawn` props; the live stroke and the rubber band are written straight to the DOM by `showLiveStroke` / `showRubber`, deliberately bypassing React) → `RouteDrawing.tsx` (the draft, the keys and the confirm call) → `AdminPage.tsx` mounts it on the «Маршруты» tab. **The map emits *pieces*, it does not own the line** — a drag gives a trail, a click gives one point, and `RouteDrawing` accumulates them; see the draft trap in §10. **The wheel handler is a native listener with `passive: false`, not `onWheel`** — React registers `wheel` passively on the root, so `preventDefault()` inside `onWheel` is silently ignored and the page keeps scrolling while the map zooms under the cursor. Moving it back to `onWheel` looks tidier and breaks exactly that |
| Change who may sign in, or what a group grants | `AUTH_ADMIN_GROUPS` in `.env` first — group names are configuration, not code. Only if a **new kind** of right is needed: `Permission` in `domain/auth.py` → `permissions_for` → the `require_*` dependency in `presentation/http/auth.py` → the guarded routers. Never read `groups_raw` to decide access |
| Change the login/logout flow itself | `presentation/http/routers/v1/auth.py` (redirects, `state`, cookie) → `application/services/auth_service.py` (JIT upsert, session) → `infrastructure/auth/keycloak.py` (code exchange, JWKS). Frontend side: `components/LoginGate.tsx` and the gate in `App.tsx` |
| Change who can see hidden cities/routes/assignments | `include_inactive` threads through `list_cities` / `get_city` / `list_assignments` / `get_assignment` (repository → service → router → `api.ts`). Only the admin panel passes `true` |
| Change catalogue parsing (new column, new format) | `infrastructure/catalog/parser.py` only; the row/point types live in `domain/catalog.py` |
| Retune catalogue distance thresholds | `MERGE_DISTANCE_M` / `DIFF_DISTANCE_M` / `CITY_BOUNDS_MARGIN_M` in `domain/catalog.py` |
| Change how a catalogue pack is uploaded or a revision rolled back | `components/CatalogImports.tsx` (admin only). `CatalogPage.tsx` is the read-only directory and must stay that way |
| Change the «Как завести город» manual, or add a second one | `pages/ManualCityPage.tsx` (the page and the Overpass query) → `MANUAL_CITY_PATH` + the `manual` variant in `routing.ts` → `App.tsx` (render + backlink to `/admin`). The page fetches nothing and **is deliberately outside `require_admin`** — see §10. The Overpass query lives only in that file; `docs/pipeline-and-metrics.md` describes the page but does not copy the query, so the two cannot drift |
| Add a section to the admin panel | a component under `components/`, mounted from `AdminPage.tsx`. City-scoped → a tab in `CITY_TABS`; not city-scoped → a page-level section in `AdminSection` (like `AdminUsers.tsx`). Keep the two switchers visually different — underlined text for sections, pill tabs inside a city — or they read as one level. Guard its writes with `require_admin` in the same change |
| Change the people directory | `user_service.py` → `users.py` router → `AdminUsers.tsx` — creation, renaming and hiding all live there. `UserSelect.tsx` only selects; do not put a create form back into it (see §10). **A person is attached to a row in exactly two roles, and both are named `uploaded_by`**: `pipeline_runs.uploaded_by_users_id` (who brought the video) and `catalog_imports.uploaded_by_users_id` (who brought the catalogue pack). The third is `assignments.author_users_id` — the person who *set* the campaign, a different thing. **Who drove and filmed is not stored at all** — see §10 |
| Change how the shooting date is entered | `useVideoUpload.ts` (`shotDate` per queued file, `shotStartedAt()` decides what is sent) → `DateField.tsx` + its mount in `UploadPage.tsx` → `createRun` in `api.ts` → `CreateRunRequest` / `UpdateShootingRequest` → `pipeline_run_service` → repository → the `PipelineRun` model and `0001_schema`. Use the shared `DateField`, never a native `<input type="date">`: the browser owns that popup and renders it outside the product theme. Date↔ISO conversion belongs in `utils/formatters.ts` and nowhere else — see the timezone trap in §10. Preserve the invariant at every layer: create requires `shot_started_at`, PATCH may omit it but may not send `null`, and the database column is `NOT NULL` |
| Change what the overlay card shows | `../ai_ad_ml/ml/pipeline/scripts/viewer/payload.py` + `OverlayObjectPayload` in both copies of `pipeline_contracts/artifacts.py` + `../ai_ad_frontend/src/components/VideoOverlayPlayer.tsx` |

---

## 8. Commands

```bash
docker compose up -d --build       # backend + migrations + Postgres + MinIO
docker compose down                # run separately in every repository
uv run python -m alembic -c alembic.ini upgrade head
uv run python -m uvicorn main:app --app-dir src --reload
uv run pytest                # needs postgres up; creates/drops ad_pipeline_test
uv run ruff check . && uv run mypy .
cd ../ai_ad_frontend && docker compose up -d --build
cd ../ai_ad_frontend && pnpm dev
cd ../ai_ad_frontend && pnpm build && pnpm lint
cd ../ai_ad_ml && docker compose up -d --build
cd ../ai_ad_ml && uv run python -m processing_worker.main
cd ../ai_ad_ml && uv run pytest && uv run ruff check . && uv run mypy .
cd ../ai_ad_ml && ./run_video_pipeline.sh path/to/video.mp4  # standalone GPU run
```

**Run `ruff`, `mypy` and `pytest` after every change, and `pnpm lint` after every frontend change.**
All four are expected to be clean — that is the baseline, not an aspiration. `mypy` in particular
only works as a signal while it stays at zero: it sat at 26 errors for a while, none of them real
bugs, and the one consequence was that nobody looked at it. If a finding genuinely cannot be
expressed in types, silence it at the single line with `# type: ignore[code]` **and a comment saying
why** — never by widening a signature or excluding a module.

Backend tests use a session-scoped autouse `database` fixture that creates the test database before
collection and calls `pytest.exit` when Postgres is unreachable. ML/scoring tests live in
`../ai_ad_ml/tests/` and do not need PostgreSQL.

---

## 9. Conventions

* **Layering:** presentation → application (services/DTOs) → domain (pure) → infrastructure.
  Services never import FastAPI; domain imports nothing project-specific.
* **DTOs:** application DTOs in `application/common/dto/`, HTTP response models in
  `presentation/http/dto/response.py`. Artifact readers validate the full shared CSV contract, but
  browser DTOs are deliberately narrow: `RunObjectDTO` exposes only the seven fields the result UI
  consumes instead of leaking the full `TrackCsvRow` over HTTP.
* **Authentication: corporate Keycloak (OIDC), whole app behind it.** People sign in with their
  Active Directory account at `IC-GROUP` on `ssoc.ic-group.ru`; the app never sees a password and has
  no login form of its own. Every `/api/v1` endpoint requires a session — the router applies
  `current_user` to all of them and exempts exactly one thing, `/auth/*`, so a new endpoint is closed
  by default. `/healthcheck` stays open (monitoring cannot log in) and `/internal/v1` keeps its own
  shared token (machine-to-machine, no human involved).
  * **BFF, not a bearer token in the browser.** `/auth/login` redirects to Keycloak, `/auth/callback`
    exchanges the code for a token **server-side**, verifies its signature against JWKS, and stores a
    row in `user_sessions`. The browser gets only an opaque `HttpOnly` cookie. Three reasons, each
    sufficient on its own: a corporate token carrying dozens of AD groups overflows the 4 KB cookie
    limit and header limits; the token lives 8 hours and cannot be revoked, so a server-side row is
    the only place to evict someone; `sessionStorage` is readable by any script on the page.
  * **The token itself is never stored.** It is needed once, at callback, to learn who arrived and in
    which groups. Nothing else acts on the person's behalf.
  * **Session lifetime comes from the token's `exp`, never its own number** — 8 hours, no refresh, so
    one working day per login. Expiry is a plain 401 and a trip back to Keycloak.
  * **Logout clears our session only** — no backchannel logout. Keycloak's SSO session is separate,
    and killing it would both break the expected "come back without retyping the password" behaviour
    and sign the person out of neighbouring apps in the same realm.
  * **Authorization is a whitelist, `AUTH_ADMIN_GROUPS`, matched exactly.** The token carries the
    whole org chart — departments, mailing lists, file-share access — and none of it means anything
    to this app. Group names are compared as exact strings: Keycloak emits full paths
    (`/Departments/Marketing`) and Russian AD names contain spaces and Cyrillic, so `startswith` or
    case-insensitive matching would hand rights to whoever owns a similarly named group. The list
    lives in configuration, not the database, because otherwise the first admin has nowhere to come
    from: the directory is empty until someone logs in.
  * **`permissions` on the `users` row is a mirror, not the source of truth** — a snapshot recomputed
    from the token's groups at every login, so the admin panel can show who is who. Access is decided
    from the current token's groups. `groups_raw` is diagnostics for "why is Petrov not an admin" and
    must never decide access.
  * What `require_admin` guards is unchanged from the password era, deliberately: every write on
    cities and routes, **both** writes on assignments, all four catalogue-revision writes, and
    **both** writes on people. **The line is the cost of a mistake, not the difficulty.**
    Administration changes the frame everyone works inside; operational work — shootings, video
    upload, geozones — stays open to any signed-in user, or the product becomes unusable: the driver
    picks a ready assignment, never invents one.
  * `allow_hidden` — `include_inactive` is silently downgraded for non-admins rather than refused.
    Hidden records are clutter, not secrets, and a refusal would hint there is something worth
    seeing.
  * **401 vs 403 is load-bearing.** 401 means "sign in" and the frontend redirects to Keycloak; 403
    means "you are signed in but may not" and redirecting would be an infinite carousel. Neither
    answer names a group — the org chart must not leak through an error message to someone already
    denied.
  * **One switch picks the mode: `AUTH_USE_KEYCLOAK`.** `true` — the domain login described above.
    `false` — a login/password form served by `/auth/dev-login` with two fixed accounts,
    `admin`/`admin` (with rights) and `user`/`user` (without). No combinations: Keycloak here is
    production-only — there is no local copy and no container for it — so until IC-GROUP issues a
    client, `false` is the only way to work, and the real flow can first be exercised on a deployed
    service. `validate_auth_setup` refuses to boot when `true` is set without a complete
    issuer/client_id/secret triple; `false` needs no configuration at all, which is the point.
    The unused half is closed at both ends: `/auth/login` answers 503 in password mode and
    `/auth/dev-login` answers 404 (not 403) in Keycloak mode. `GET /auth/mode` is the one endpoint
    open without a session — the frontend asks it to decide whether to draw a button or a form, so a
    single build serves both modes.
  * **Directory rows are created on first login (JIT).** The link is `keycloak_subject` (`sub`),
    never the login or the full name: `sub` is permanent, a domain login changes with a surname.
    `full_name` therefore lost its `UNIQUE` — real namesakes exist and the constraint would deny the
    second one a login. Rows created by hand before SSO keep a NULL `keycloak_subject`: they still
    own their history, but nobody can sign in as them.
* **API envelope:** every success response is `{"data": …}` (`OkResponse[T]`). Errors are
  `{"detail": "<Russian sentence>"}` produced by handlers in `presentation/http/exception_handlers.py`.
  Domain errors are typed exceptions in `application/exceptions.py`, never raw `HTTPException`.
* **PATCH semantics:** request models expose `changed_fields()` so only keys the client actually sent
  are updated; validation re-checks the whole invariant against stored values.
* **DB naming:** table `things`, PK `things_id`, FK `<table>_id`, timestamps `created_at`/`updated_at`
  with server defaults. Soft delete via `is_active` where history matters. **Cities, routes and
  assignments have no delete at all** — `is_active` is an ordinary `PATCH` field meaning hide/show,
  and there is no `DELETE` verb on any of the three. The cascade is why: city → routes →
  assignments → shootings, so a real delete anywhere up that chain takes the videos with it.
  Anything that hides must also be un-hideable from somewhere, or it is a one-way door (see §10).
* **Repositories** own transactions but do not commit; services call `commit()`/`rollback()`.
* **Comments** explain *why*, in Russian, and are dense in this codebase — match that density and
  keep them truthful when you edit the code they describe.
* **On screen the unit of account is «видео»; in the code and the comments it stays «съёмка».**
  Since 31.07.2026 no user-facing string says «съёмка» — the people who upload and read are holding
  a file, and a second word for it bought them nothing. Internally the two are not the same thing:
  a «съёмка» is a row in `pipeline_runs` with an assignment, a date, an uploader, a processing status
  and artifacts, and the video is what sits in MinIO — comments routinely need both in one sentence
  («исходное видео съёмки»), which a blanket rename would turn into nonsense. So: identifiers stay
  `shooting*`, comments and `docs/` stay «съёмка», **new UI strings must say «видео»**. Where the
  word meant the *act* rather than the record — «начало съёмки», «дата съёмки» — the screen says
  **«запись»**, because «начало видео» reads as a timestamp inside the file. Three strings had to be
  rewritten rather than substituted, and they are listed in the changelog entry for that date.
* **Frontend:** no state library, no router library; `fetch` wrapper in `api.ts`, types mirrored by
  hand in `types.ts`. Keep them in sync with backend response DTOs manually.
* **Server data fetched by an on-page selection is stored with a tag saying whose it is, and read
  through a derived guard — never cleared in an effect.** The shape is always the same:
  `useState<{ key: …; items: … } | null>(null)`, then
  `const ofCurrent = loaded?.key === currentKey ? loaded : null`. `VideosPage.tsx` (routes,
  assignments), `UploadPage.tsx` (city detail, assignments) and `CatalogPage.tsx` (structures,
  revisions) all use it — copy it, do not invent a hook, or there will be a fourth way to do one
  thing. `null` additionally means "not loaded yet", which is what lets a screen say «Загружаем…»
  instead of lying «пусто» for half a second on every switch.
  **This is not cosmetic.** Pages keyed by a route param are safe — `App.tsx` gives them a `key`, so
  they remount and stale state cannot survive. Pages driven by a dropdown do not remount, and in
  `UploadPage` that window was a data bug, not a flicker: the assignment picker kept the previous
  city's options while the new city was already shown, `destinationReady` still saw the old id, and
  a shooting could be uploaded into another city's assignment — which then quietly skewed that
  route's metrics. A selection derived from fetched data (`activeAssignment`) must be validated
  against the list that is on screen *now*, not merely stored.

---

## 10. Gaps and traps you must know about

* **Two meanings of "object".** In the pipeline `object_id` is a cluster of detections inside one
  video — the next drive-by gives the same billboard a different number. In the catalogue an
  `ad_structure` is the physical billboard. Russian docs and UI say «находка» for the first and
  «конструкция» for the second; keep that split.
* **The catalogue's identity is the coordinate, not the address.** Source addresses are free-form
  («у д. 4Б по Крепостному ш.»), and rows repeat: 8–10 rows per coordinate are separate surfaces at
  one spot. They collapse into one row with `surfaces_count`; never dedupe by address.
* **Catalogue revisions**: `catalog_imports.is_current` is the single source of truth for visibility —
  `ad_structures` has no flag of its own. Rollback flips two rows and must never rewrite structures.
  **"No current revision" is a legal state** — it is what a city looks like before anything is
  uploaded, and `POST /catalog/imports/{id}/hide` puts a city back into it. Without that verb the
  first revision of a city was unremovable: nothing to roll back to, and deleting the current one is
  refused. Un-hiding is plain `restore` — no second verb, and the button was already there.
* **Three functions in `api.ts` bypass `apiFetch`, and each needs `adminHeaders()` by hand.**
  `uploadGeometry` and `uploadCatalogImport` build multipart bodies, `apiDelete` handles the empty
  204 — none of them go through the wrapper that attaches the password and clears the session on
  401. Putting `require_admin` on an endpoint reached through one of them and forgetting the header
  produces the worst possible symptom: a screen that is already behind the login form answers
  «введите логин и пароль». Guard an endpoint → check which of the three reaches it.
* **The system stores who *uploaded* a video, never who *shot* it — and that used to be two names for
  one column.** `pipeline_runs.operator_users_id` said «оператор» in the database, the DTOs, the API
  and the frontend state, while all three screens that show it said **«Кто загрузил»**. One field,
  one person, two meanings — and the neighbouring table had already settled the question, because
  `catalog_imports.uploaded_by_users_id` names the same role correctly. Renamed to
  `uploaded_by_users_id` on 30.07.2026 through every layer including the column and its index; the UI
  strings were not touched, they were right all along. **Do not reintroduce «оператор» anywhere**: the
  owner's decision is that who drove and filmed is not interesting to this product, so there is no
  field for it and no place to put one. If that ever changes, it is a *new* column next to this one,
  not a renaming of it — the two are different people the moment anyone uploads a batch from someone
  else's memory card.
* **People are created in the admin panel only — `UserSelect` selects, it never creates.** It used
  to create: a free-text field in the «Кто загрузил» dropdown, filled in by whoever happened to be
  uploading. The directory collected twins («Иванов», «Иванов А.», «иванов») faster than anyone
  could clean them, because the person entering a name was not the person responsible for the
  directory. Both `POST /users` and `PATCH /users/{id}` are behind the password now; only `GET`
  stays open, because every upload form reads it. Consequence: an empty directory blocks uploading —
  `UserSelect` says so out loud instead of showing a silent empty dropdown. There is no delete: a
  person stands as the author of shootings and imports, so `is_active` hides them from the dropdowns
  and the same screen brings them back.
* Coefficient tables are **defaults, not calibrated numbers** — area, position, contrast and
  confidence were set so work could proceed. Calibration against a real distribution is still open.
* The standalone `../ai_ad_ml/run_video_pipeline.sh` intentionally exposes only arguments accepted
  by `run_pipeline.py`; the former conditional `--brand-overrides` argument was removed during the
  repository split because no such CLI option exists.
* α is derived from `final_brand_conf` only; detection history is not an input to this coefficient.
* An object that was never classified still gets α = 0.5 (the floor) and counts as `other`.
* β needs `duration_sec`; it exists only after `mark_completed`. The only remaining way to get a
  neutral β is an unmarked route — every shooting has a route now, so it always has zones, sometimes
  none of them.
* **A shooting cannot exist outside a route, and `pipeline_runs.assignments_id` is `NOT NULL`.**
  Uploading "without an assignment" is gone: no route meant no geozones, so no significance and
  nowhere to roll the shooting up — the video took storage and answered no question. The FK is
  `CASCADE`, not `SET NULL`: there is nothing to null out. **`PipelineRunDTO.assignment` and its
  frontend twin stay optional anyway** — there `None` means "the relation was not loaded", which is
  how the internal processing claim and `GET /assignments/{id}/runs` both answer. Tightening that
  field to non-optional breaks those deliberately lightweight reads.
* **The upload page's target comes from the loaded assignment, not from the id in the URL.**
  `UploadPage` in pinned mode (`/upload?assignment=…`) reads `pinnedAssignment?.id`, never
  `assignmentId` — otherwise a tab opened before the assignment was hidden keeps a live "Начать
  загрузку" and fails per file on `POST /runs`. Same shape as the dropdown case in §9: a target
  derived from fetched data must be validated against what actually loaded, not merely stored.
* Geozone validation is split: bounds (`0 ≤ start < end ≤ 1`) in `catalog_service`, overlap detection
  in `sql_catalog_repository` under a route row lock (`GeozoneOverlapError` → HTTP 409).
* **A route is drawn, not uploaded — and the reason is the shape of the result, not convenience.**
  Until 30.07.2026 a route's line came from OSM as a geojson file. What arrived was a *bag of
  segments*: connected, but with branches (38 branch nodes in Simferopol's route-1) and with no
  order at all. `RouteMap.tsx` therefore carried `orderRouteSegments`, a "nearest endpoint from the
  westernmost point" heuristic, purely so the thing could be animated. A drawn route is **one
  ordered LineString** by construction — it has a start, an end and a length — so that heuristic is
  gone with the upload. Consequence: `route_line_collection` in `domain/geometry.py` is the only
  writer of route geometry.
* **The seed stops at the road layer — routes come up with no line, on purpose.** For three days
  after the upload was removed, `0002_seed` still seeded the seven old OSM bags: the routes rendered,
  so nothing looked broken, and that was the problem — a seeded bag has no order, no start and no
  length, and it claims `has_geometry: true` on a route nobody has drawn. Removed on 31.07.2026. The
  seven files are not deleted: as *seed* they lied, as *fixtures* they are the only real-data
  yardstick the snapper has, so they moved to `tests/fixtures/routes/` and
  [tests/test_route_snapping.py](tests/test_route_snapping.py) keeps tracing all seven. Two things to
  keep straight if you touch the seed: the road layers stay (`export.geojson` is a genuine migration
  asset — without it there is nothing to draw on and no city bounds for the catalogue parser), and
  `geometry` must be **omitted from the insert**, never passed as `None` — the migration's
  `sa.table` uses a plain `postgresql.JSONB`, which writes Python `None` as the JSON literal `null`,
  and the model's `none_as_null=True` does not apply because `bulk_insert` goes around the model.
  That is the §10 JSONB trap in its least visible form: the flag would read `true` on an empty line.
* **The drawn line is a draft that survives `pointerup` — the map has no idea when it is finished.**
  Until 31.07.2026 one drag *was* the line: `pointerup` fired `onStrokeDrawn` and `drawing` went
  false. That made a 40 km route a 40 km hostage of one held mouse button — you could not release to
  zoom, to look around, or to breathe, and a junction you could not safely drag through had no
  answer at all. Now `RouteMap` emits **pieces** (`onSegmentDrawn`): a drag gives its trail, a click
  under `CLICK_SLOP_PX` gives one point, and `RouteDrawing` appends both to a draft that ends only
  on «Подтвердить». Four things hold this together and are easy to break one at a time: the draft is
  stored **as segments**, not as a flat point list, because that is what makes «Шаг назад» undo one
  *action* (a whole trail or a single click) instead of one point; the live stroke and the rubber
  band are both drawn **from the last draft point**, or each piece would look like a separate line;
  `paused` (Esc) stops input **without clearing anything**, which is the only state in which
  «Подтвердить» cannot be spoiled by a stray click; and undo is deliberately **one step deep** —
  the owner asked for exactly that, so `undone` blocks the second Ctrl+Z until a new piece arrives.
  The keys are accelerators only, and their names are printed on the buttons — this screen is opened
  once every few months, when a new city is set up, and nothing here may be invisible.
* **Clicking is cheap, but a rare click is not — the snapper fills the gap with the *shortest* path.**
  Between two stroke points the matcher is free to choose the road, so a line set by sparse clicks
  quietly straightens out the places where the real route made a detour. Measured on the seven real
  routes with the same ±20 m hand error: clicking at every 20° turn and at least every 300 m keeps
  the length within 0.1–3.8 % (worst 11.7 %), every 400 m already reaches 12.4 %, and every 800 m
  drifts to +25 % / −21 %. `test_route_set_by_clicks_recovers_too` in
  [tests/test_route_snapping.py](tests/test_route_snapping.py) pins the first regime, and the hint on
  screen states it in words. If someone asks to «упростить» the drawing so fewer clicks are needed,
  that is this trade-off being asked for again — bring the measurement, not an opinion.
* **Snapping lives on the backend because the computation happens once, on «Подтвердить».** The
  stroke is matched to the road network for the stroke *as a whole* — where each point lands depends
  on where the line goes next — so it cannot run incrementally while the hand is still moving. Given
  that, a round trip costs nothing next to the ~60 ms of graph building, and it buys a pure domain
  module under ordinary pytest instead of a map-matching engine in the browser with no test runner.
  Do not "optimise" this into the frontend without first bringing a test story for it.
* **The road graph must be densified, and this is load-bearing.** `RoadGraph.from_feature_collection`
  splits every edge to at most `DEFAULT_MAX_SEGMENT_M` (20 m). It is not a performance knob. Raw OSM
  edges have a median length of ~22 m but a tenth exceed 80 m and the longest approach 500 m; on such
  an edge a position "halfway along" cannot be represented, consecutive stroke points grab opposite
  endpoints, and stitching faithfully lays a path out and back. Measured: **without densification the
  route length inflated by 24–250 % under every combination of the scoring weights.** Densifying
  doubles the node count (8 k → 18 k) and costs milliseconds. The parameter sweep also showed the
  opposite: `SnappingConfig`'s weights barely matter within sane ranges. Tune the graph, not the
  numbers.
* **When testing the snapper, model the hand as a *smooth* error — otherwise you measure nothing.**
  The obvious synthetic stroke (jitter every reference point independently) is a sawtooth: reference
  vertices sit ~20 m apart, so ±40 m of per-point noise produces a line that genuinely zigzags, and
  any correct matcher follows the zigzag. The first version of these tests did exactly that and
  reported 24–250 % length error — a failure of the *model*, not the engine. `_hand()` in
  [tests/test_route_snapping.py](tests/test_route_snapping.py) draws the offset from knots every few
  hundred metres and interpolates between them; with it, ±20 m of hand error recovers six of the
  seven real routes to within 0.8 %.
* **`JSONB` needs `none_as_null=True`.** By default SQLAlchemy writes Python `None` into a JSONB
  column as the JSON literal `null`, so `IS NOT NULL` is true and "geometry not loaded" becomes
  indistinguishable from loaded. Both geometry columns declare `JSONB(none_as_null=True)`; any new
  nullable JSONB column must do the same.
* **Geometry never travels in a list response.** `cities.roads_geometry` is up to 1.5 MB. Every query
  that loads `City` or `Route` models carries `defer(...)` on those columns, and DTOs expose only
  `has_geometry` / `has_roads_geometry`. `_route_to_dto` takes the flag as an argument on purpose —
  reading `route.geometry` there would undo the deferral. Geometry has its own endpoints with `ETag`.
  **This is no longer an honour system:** [tests/test_geometry_deferred.py](tests/test_geometry_deferred.py)
  listens to the SQL that actually reaches Postgres and fails if `roads_geometry` is selected by an
  endpoint that has no business loading it. The rule needed teeth — `sql_ad_catalog_repository.py`
  had fallen out of it entirely, and `GET /ad-structures` was paying 12 ms per request to fetch
  755 KB of JSONB it then threw away. Note the distinction the test encodes: `roads_geometry IS NOT
  NULL` is a *legal* mention — that is how `has_roads_geometry` is computed, in the database, so only
  a boolean crosses the wire. Referencing the column is fine; selecting its value is not.
* **Nothing in the app ever handles a password, and that removed a whole family of traps.** Until
  06.08.2026 the admin panel had its own HTTP Basic password, and making it work with a Cyrillic
  value took a `HTTPBasic` subclass (the library decodes the header as ASCII and raises before your
  dependency runs), byte comparison in place of `secrets.compare_digest` on `str` (which raises
  `TypeError` on non-ASCII, surfacing as a 500), and a hand-rolled UTF-8 base64 in the frontend
  because `btoa` is latin1-only. All of it is gone: passwords are typed on Keycloak's page, and the
  fallback login exists only while `AUTH_USE_KEYCLOAK=false`. Do not reintroduce a password field
  anywhere without re-reading this — the encoding traps are still there, they just have nothing to
  bite.
* **The login screen must never guess.** `App.tsx` asks `GET /auth/mode` before drawing anything and
  distinguishes four answers: Keycloak, password form, *configured-but-unusable*, and *no answer at
  all*. An earlier version collapsed the last two into "assume Keycloak", and the result was a
  working-looking «Войти» button that led to a 404 while the real cause was a stale backend. The
  same rule applies to `AUTH_USE_KEYCLOAK=true` without credentials: the service starts (crashing the
  whole app over one unset variable is worse than the outage it prevents), logs the reason, and the
  screen says the domain login is not configured. **It must never fall back to the password form** —
  that is the one degradation that silently opens a door on a deployed stand.
* **The city manual sits outside the password on purpose, and the reason is the router, not the
  content.** `/manual/city` describes admin work, so putting it behind `require_admin` looks
  obviously right — it would break the page. The admin panel's tabs live in component state, not in
  the address (deliberately: «админку не шлют ссылкой»), so a link that goes through the login form
  can only land on the panel's first screen. A manual reachable only by logging in and then not
  arriving is not reachable. It is also pure text — no `apiFetch`, nothing to leak — and it explains
  a third-party public service plus our own button labels. Any further manual inherits both
  properties: **no data fetching, no password.** The moment one needs a backend read, it stops being
  a manual and the whole placement has to be reconsidered.
* **There is exactly one video per shooting, and the pipeline never writes a second one.** The player
  draws boxes over the *source* video from `overlay.json` — see `VideoOverlayPlayer.tsx`, which is
  handed `playback.source_url`. Until 29.07.2026 the pipeline also burned the boxes into a full copy
  (`annotated_video.mp4`): on a 7.7-minute 1080p drive that was 1.01 GB next to a 1.07 GB original —
  **46 % of all storage** — and for video input it was produced by decoding and re-encoding the whole
  source a second time. Nothing read it: no component touched `annotated_url`, and `api.ts` has no
  artifact functions at all, so it was not even downloadable. If you find yourself wanting to render
  boxes into a file, the answer is almost certainly `overlay.json` plus the player instead.
* **A worker without a GPU starts happily and only fails on the first video.** `PIPELINE_DEVICE`
  defaults to `"0"`, but nothing touches CUDA until a run is claimed and the models load — so the
  native queue process can look healthy before the first real shooting reports failure. Verify the
  selected device and `torch.cuda.is_available()` before allowing it to claim work; use a supported
  CPU setting explicitly only when that runtime is acceptable.
* **Uploading a city's road layer recomputes `bounds_*` in the same operation.** The catalogue parser
  uses that box to drop out-of-town points; a new layer with a stale box silently discards good rows.
* **`ShootingMetricsDTO` is the unit of account at every level.** Assignment and route both read it;
  nothing aggregates aggregates. A route summary therefore re-reads `tracks.csv` for every completed
  shooting on the route — that is why `RoutePage` refetches its summary only when the completed count
  changes, not on the 5 s assignment poll. **Since 30.07.2026 it is also gated on the analytics tab
  being open** (`?view=analytics`): the operational half of both pages — the assignment cards, the
  video cards, the page header — is built entirely from cheap reads (`getCity`,
  `getRouteAssignments`, `getAssignment`, `getAssignmentRuns`), so opening a route to find one video
  no longer pays for the rollup of every shooting on it. The assignment header's «отснято» is summed
  from the runs in the browser for exactly this reason; it used to come from the rollup.
* **Visibility has no cross-brand total in the API.** The final business measure is
  `brands[].sum_visibility_value` for one brand in one shooting; assignment and route keep the same
  split in `brands[].visibility_per_shooting`. Summing unlike brands into
  `totals.visibility_index` created a number with no business meaning, so that field — together with
  the total rollup `visibility_per_shooting` — was removed on 04.08.2026. The frontend may sum brand
  values transiently only to turn each one into a share; the sum must not become a tile, DTO field or
  stored fact again.
* **The DWH fact is produced by the backend summary calculation, never by worker or SQL.** β needs
  `duration_sec`, so `ProcessingJobService.complete` first calls `mark_completed`, then
  `PipelineRunService.append_dwh_revision`, and commits artifacts, status and facts together. The
  writer locks the run, takes `max(revision) + 1` and only inserts: old rows are immutable. One row is
  one brand in one shooting revision; no-brand is represented by one NULL/NULL row so a completed
  shooting does not disappear from the extract. IDs have no FKs intentionally and are accompanied
  by city/route/assignment names: this is an outbound history table and its rows must stay readable
  without operational JOINs. Today only successful processing invokes the writer; the trigger that
  appends another revision after a geozone recalculation is still a separate next step.
* **Hiding without a way back is a one-way door — the bug that cost every city at once.** Before
  28.07.2026 `DELETE /cities/{slug}` set `is_active = false`, the list filtered it out, the slug
  stayed taken and no endpoint could flip it back: the owner "deleted" three cities and could
  neither see nor recreate them. Now `is_active` is a plain `PATCH` field and the admin page — and
  only it — passes `include_inactive=true`. **Any future soft-hide must ship its un-hide in the same
  change, and the screen that can hide must be able to show.** The assignment's hide (29.07.2026)
  followed that rule from the start: «Скрыть» and «Показать» are the same button in
  `AdminAssignments.tsx`, and `update_assignment` reads the row with `include_inactive=True` on
  purpose — a 404 on "показать" would be the one-way door all over again.
* **Hidden means gone everywhere, including direct URLs.** `get_city` and `get_route` return `None`
  for inactive rows unless `include_inactive` is set, so a bookmarked `/archive/kerch` gives 404.
  The two admin write paths (`update_route`, `draw_route_geometry`) pass `include_inactive=True` on
  purpose — they answer about the very row they just hid, and a 404 there would read as a failure.
* **Both centre estimates ship in every brand rollup; the choice is presentation-only.**
  `MetricStat` carries `mean`, `median` and `std` together — switching is a re-render, never a
  request, and the backend never learns which one is on screen. A future per-video DWH fact stores
  the final value for each brand; DWH can derive either centre from those rows instead of persisting
  an aggregate of aggregates.
* **Under median the brand shares do not add up to 100 %.** Median is not linear — the median of a
  sum is not the sum of medians. This is a property of the estimate, not a bug; the pie chart's copy
  says so out loud under median. It is also why `visibility_share` no longer exists in the API: the
  share depends on the selected estimate, so it is computed in `RollupCharts.tsx` where the selection
  lives. Do not put it back on the server.
* **σ is shown for both estimates on purpose.** It describes the sample of shootings — how far the
  drives spread apart — not the centre estimate, and "can I trust this number" is the same question
  either way.
* **Exactly two things remove a shooting from a rollup, and both work the same way — by shortening
  the list before `metrics_rollup`, never by changing how it computes.** They are the route's date
  period and a hidden assignment. Anything else that ever needs to exclude shootings must join them
  at that seam (`list_route_runs`), because a second implementation of mean/median/std would silently
  drift from the first and the number under a filter would stop matching the number without one.
  Hiding is the only *deliberate* exclusion: it takes an admin action, it takes the assignment's
  shootings with it, and it is reversible — "показать" puts them back into the average. Note what
  this costs: a route's history changes retroactively when someone hides a campaign, and that is
  intended, not a bug to guard against.
* **A shooting is still never dropped for being *bad*, and that rests on an unchecked assumption**:
  the video covers the whole drive from A to B. A truncated upload is invisible to the system — the
  zones simply shift, because β is a fraction of *this* video's duration, and the numbers go quietly
  wrong. Rejected deliberately (owner: every drive is uploaded whole); if the assumption ever breaks,
  filtering belongs in `metrics_rollup.py` and nowhere else.
* **Hiding an assignment is a product read filter, never a processing write filter.**
  `SqlPipelineRunRepository.get` returns `None` for a shooting of a hidden assignment, so one
  line covers the card, the summary, the objects, the timeline and the player at once; `list_runs`
  excludes them through the same subquery that already resolves route and city. Write paths
  (`_get_model` directly: `claim_next`, `mark_upload_complete`, `mark_completed`, `mark_failed`,
  `add_artifact`) have no filter and must not grow one — the internal processing service invokes
  those paths on the ML worker's behalf. A hidden assignment would otherwise mean a
  queued video nobody claims and nobody hears about again. The one deliberate exception is
  `complete_upload`, which passes `include_hidden=True`: the file is already in MinIO, and refusing
  there would strand the row in `uploading` next to an orphaned object. Same reason
  `SqlPipelineRunRepository.lock_assignment` returns `False` for a hidden assignment — that check
  belongs to *starting* an upload, not finishing one.
* **A single-column index whose column is the first column of a composite one is dead weight, not a
  fallback.** Postgres serves a leftmost-prefix lookup from the composite, so
  `ix_pipeline_runs_status` next to `ix_pipeline_runs_queue (status, created_at)` — and
  `ix_catalog_imports_cities_id` next to `ix_catalog_imports_city_current (cities_id, is_current)` —
  answered nothing the composite did not, while being rewritten on every insert. Both were dropped on
  30.07.2026 along with `pipeline_runs.worker_id` (written by the old in-repository worker and read by
  no query). The standalone worker does not send or persist a worker id. The models carry a comment
  at each site
  saying why there is no `index=True`; do not "restore" one. **Before adding `index=True`, check
  `__table_args__` for a composite that already starts with that column.**
* **`pipeline_run_events` is a write-only table, and the only thing guarding it is one test.** The
  ML worker reports each stage over HTTP and backend appends the row; nothing in the product reads
  them. Progress on screen comes from
  the run's own `stage` / `progress` / `status_message`, which always hold the latest state — a
  second source of the same thing is what the events read path was, and it served `GET
  /runs/{id}/status`, an endpoint byte-identical to `GET /runs/{id}` that `api.ts` never called.
  Deleted on 30.07.2026 along with `/artifacts` and `/artifacts/{id}/url` (also uncalled), the
  `events` field on the run DTO and response, `PipelineRunEventDTO`, `RunEventResponse`,
  `ArtifactUrlDTO`/`Response`, `with_events` through three layers, and **the `events` `Relationship`
  on both models** — whose only remaining trace was `noload(PipelineRun.events)` repeated in four
  queries to stop a lazy load of something nobody read. Two consequences to keep straight: **the
  writes stay** (`add_event` from seven call sites — that is the trail you read by SQL when a run
  breaks), and because no code path reads the table any more, a broken insert would now be silent.
  `TestProcessingLog` in [tests/test_shootings.py](tests/test_shootings.py) exists for exactly that
  and must not be deleted as "a test of nothing". If a processing log ever needs to appear on screen,
  add the `Relationship` back — it is two lines — rather than reviving the endpoint.
* **`artifacts` on `PipelineRunDTO` is for the backend, not the browser.** It stays on the
  application DTO because `_find_artifact` resolves `tracks.csv`, `detections.csv`, `overlay.json`
  and the source video out of it — that is how `/summary`, `/objects`, `/timeline`, `/overlay` and
  `/playback` all work. It is deliberately **absent from `PipelineRunResponse`**: no screen can do
  anything with an object key, and `api.ts` has no artifact functions at all. Do not "expose it for
  completeness" — that is what was just removed.
* **A repository method written into the wrong class is invisible: nothing fails, the check simply
  never runs.** `lock_assignment` existed twice for a day — the correct version, with the
  `is_active` check, in `SqlCatalogRepository`, and a version without it in
  `SqlPipelineRunRepository`. Only the second was ever called: `PipelineRunService` holds an
  `IPipelineRunRepository`, and `ICatalogRepository` never declared the method at all, so the good
  copy was unreachable from any interface. Both files compile, both typecheck, and uploading into a
  hidden assignment kept working while every other screen hid it. `count_assignment_runs` had drifted
  the same way, byte-identical in both classes. **The rule this leaves:** before adding a method to a
  repository, check which Protocol the calling service actually holds — the two SQL repositories
  share a session and several models, so a method lands plausibly in either, and the wrong one is
  silent. A cross-repository duplicate is a defect by itself, never a convenience.
* **A date-only string is UTC to `new Date()`, and that silently moves the day.** `new Date('2026-05-03')`
  is parsed as UTC midnight by spec, while `new Date(2026, 4, 3)` is local midnight. West of Greenwich the
  first one lands on the previous day, so a person picking the 3rd would store the 2nd — no error, no
  warning, just a shooting on the wrong day. Hence `isoFromDateInput` in `utils/formatters.ts` builds the
  date from numbers. Keep this conversion there — a second copy is how the bug comes back.
  `shot_started_at` is also the axis the route date filter uses, so a day off here is a shooting that
  falls out of the wrong period. **The upload date is never inferred:** every queued file starts with an
  empty required date. In particular, do not bring back `File.lastModified`; after a copy from a memory
  card it can describe the copy, not the shooting.
* **The route's date period is filtered on the server, and that is not an accident.** The route summary
  already ships every shooting separately, so filtering it in the browser looks free — it is not. Mean,
  median, std and the per-brand zero-fill ("a brand missing from a shooting is a zero, not a skip") would
  need a second implementation in TypeScript, and the two would drift silently: the number under a period
  would stop matching the number without one. §7 says `metrics_rollup.py` is the only place that decides
  how shootings collapse; a period must therefore only **shorten the list before it**, never re-implement
  it after. The picker keeps both boundaries in a local draft and refetches only on **Apply**; that
  request still re-reads `tracks.csv` for every shooting.
  Two consequences of the same rule: `assignments_total` counts the assignments **among the shootings
  that fed the number**, not the route's total, or the caption "собрано из N заданий" lies under a
  period; and the window travels as instants, not calendar dates — only the browser knows the user's
  timezone, and it is the browser that adds a day to the end so the last selected date is included whole.
* **The shooting date is per uploaded file, never per batch.** Twenty videos in one upload are usually
  twenty separate drives, sometimes on different days, and the route chart is plotted by
  `shot_started_at` — one shared field would collapse them onto a single point with nothing on screen
  to reveal it. The field is prefilled from file metadata, which lies after a copy from a memory card
  (it carries the copy time). If the date is left untouched the full file timestamp is sent, hours
  included, because same-day drives order by it; once the date is edited the hours are fiction, so
  midnight goes instead. **The date cannot be cleared:** the upload button is disabled while any
  file has an empty date, `POST /runs` requires an aware `shot_started_at`, PATCH refuses an explicit
  `null`, and `pipeline_runs.shot_started_at` is `NOT NULL`. An undated shooting has no legal state
  because it cannot be placed on the route chart or in a date window.
* **Zones are stored as fractions, entered as percent.** The API only ever sees `[0,1]`; the ×100 is
  purely a UI affordance in `RouteGeozones.tsx`. Minutes were rejected on purpose — different drives
  have different durations, so "minute four" is a different place each time.
* `route_geozones.description` is `NOT NULL DEFAULT ''` — empty string, never NULL. `PATCH` with `""`
  clears the text; `PATCH` with `null` is a 400, same as every other field of a zone.
* Tests rely on cities/routes seeded **by migrations** (`simferopol/route-1`, sevastopol) and truncate
  only mutable tables between tests.
* `README.md` predates the metric rewrite; §"Как проходит обработка видео" is still accurate, metric
  statements are not.
* "Visibility percent" is presentation-only: share within one video, computed in `RunCharts.tsx`.
  There is no absolute scale, and the unit of `V` (seconds × dimensionless coefficients) is not
  interpreted anywhere.

---

## 11. Documentation protocol (do not skip)

After any change that alters behaviour, update **both** documents in the same change:

* this file — if you changed structure, flow, contracts, conventions, commands, or added a trap;
* [docs/pipeline-and-metrics.md](docs/pipeline-and-metrics.md) — if you changed anything the owner
  reads: formulas, coefficient tables, thresholds, storage layout, what a screen shows. Its
  changelog section at the bottom gets a dated line.

Triggers that always require a doc update: a formula or coefficient table changes; a CSV/overlay
field is added, renamed or removed; a DB table or column changes; an endpoint appears or disappears;
a pipeline stage is added, removed or reordered; a default threshold moves; a gap listed in §10 is
closed or a new one appears.

If a document turns out to be wrong, fix the document — do not add a second document describing the
same thing. Two overlapping documents about one subject is how documentation rots.
