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
4. **Artifact/DTO shapes live in `pipeline_contracts/`.** That package is the single source of truth
   shared by the ML pipeline and the backend. `ml/pipeline/scripts/artifacts.py`,
   `ml/pipeline/scripts/domain.py` and `apps/backend/src/domain/entities/` are thin re-export
   facades — do not add logic there.
5. **Tunable numbers go into config dataclasses**, never into `if` branches:
   [ml/pipeline/scripts/config.py](ml/pipeline/scripts/config.py) (`ScoringConfig` and friends).
   Business tunes tables without touching code.
6. **Do not run the full pipeline unless asked.** It needs a GPU, model weights
   (`models/*/best.pt`, gitignored) and a real video. Prefer unit tests.
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
| `pipeline_contracts/` | **Shared contracts**: CSV row models, overlay payload, enums (`PipelineRunStatus`, `PipelineRunStage`, `PipelineArtifactType`, `FinalStatus`, …), brand constants. Imported by both ML and backend. |
| `ml/pipeline/run_pipeline.py` | CLI entry point (argparse → `PipelineConfig` → `run_pipeline`). |
| `ml/pipeline/scripts/runner.py` | Stage orchestration. The one file that shows the whole ML flow. |
| `ml/pipeline/scripts/scoring/` | The metric: `area`, `position`, `contrast`, `intensity`, `attention`, `confidence`, `geometry`, `interpolation`. Feature extraction is separate from assembly. |
| `ml/pipeline/scripts/` (rest) | `detection`, `crops`, `quality`, `classification`, `tracking`, `track_groups`, `aggregation`, `io`, `schemas`, `config`, `visualization`. |
| `ml/pipeline/scripts/reporting/` | CSV + charts + `report.html` (standalone pipeline reports, **not** the product UI). |
| `ml/pipeline/scripts/viewer/` | `overlay.json` + `viewer.html` (standalone player with cards). |
| `apps/backend/src/domain/` | Pure logic, no I/O: `geozones.py` (`beta`, `overlaps`), `catalog.py` (point collapsing, revision diff, city bounds), `geometry.py` (geojson validation, bbox) + entity facades. |
| `apps/backend/src/application/` | Services (`pipeline_run_service`, `catalog_service`, `metrics_rollup`, `user_service`), DTOs, repository interfaces. |
| `apps/backend/src/infrastructure/` | SQLModel models, SQL repositories, MinIO storage, `catalog/parser.py` (xlsx/xls/csv). |
| `apps/backend/src/presentation/http/` | FastAPI routers, request/response DTOs, DI, exception handlers, `security.py` (the admin password). |
| `apps/backend/src/worker/` | Queue worker that runs the ML pipeline out-of-process. |
| `apps/backend/alembic/` | Migrations. Exactly two since the 28.07.2026 squash: `0001_schema` (all ten tables) and `0002_seed` (two cities, seven routes **with their geometry** — tests depend on these). `seed_data/geometry/` holds the nine geojson files the seed reads; they are migration assets, not leftovers — delete them and a from-scratch database comes up with an empty map. While there is no production database the chain is squashed rather than extended; the day real data exists, that stops and history is append-only. |
| `apps/frontend/src/` | React 19 + Vite + Recharts. Hand-rolled router (`routing.ts`), no react-router. |
| `scripts/` | `dev.sh` — brings up the whole stack. |
| `tests/` | pytest. Needs a live Postgres; MinIO is faked. |
| `docs/plan.md` + `docs/plan-NN-*.md` | **Intent, not state**: accepted decisions with reasons, open decisions that block work, and the step list. Per-step detail files are deleted once the step lands and its content moves into `pipeline-and-metrics.md`. Never describe working behaviour here. |
| `README.md` | Setup/ops guide. Predates the metric rewrite; treat metric statements in it as stale. |

---

## 4. Runtime topology

| Piece | How it runs | Where |
|---|---|---|
| Postgres | docker compose | `:5432` |
| MinIO | docker compose | `:9000` API, `:9001` console |
| Backend (FastAPI) | docker compose, `--reload` | `:8000`, prefix `/api/v1`, health at `/healthcheck` |
| Worker | **local host process** (needs GPU), started by `scripts/dev.sh` | `.runtime/worker/<run_id>/` |
| Frontend (Vite) | `pnpm dev` | `:5173` (in backend CORS allowlist) |

Config: pydantic-settings, env from `apps/backend/.env` (gitignored). Pipeline knobs use the
`PIPELINE_` prefix (`PIPELINE_FRAME_STRIDE`, default **1** for the worker; the CLI default is 10).

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

⚠ **Name collision to keep straight:** in `ml/` the label `visibility_value` means **S·α** (derived
in [reporting/writer.py](ml/pipeline/scripts/reporting/writer.py) and
[viewer/payload.py](ml/pipeline/scripts/viewer/payload.py) for standalone reports and overlay cards).
On the backend `visibility_value` means **S·α·β**. They are different numbers with the same name.

---

## 6. End-to-end flow

1. `POST /api/v1/runs` → row in `pipeline_runs` (status `uploading`) + presigned PUT URL.
   Optional `assignment_id`; the assignment row is locked and capped at
   `MAX_ASSIGNMENT_SHOOTINGS = 20`.
2. Browser PUTs the file straight to MinIO: `runs/{run_id}/source/{safe_name}`.
3. `POST /runs/{run_id}/upload-complete` → registers the `source_video` artifact, status `queued`.
4. Worker `claim_next` (`SELECT … FOR UPDATE SKIP LOCKED`) → status `processing`, downloads the
   video, runs the pipeline, reporting progress into `pipeline_runs` + `pipeline_run_events`.
5. Pipeline stages: detection → tracking → classification → final aggregation → business rules →
   artifacts.
6. Worker uploads everything under `runs/{run_id}/artifacts/…`. Crops are uploaded but **not**
   registered as DB rows (`should_register_artifact`). `mark_completed` stores fps / frame_count /
   frame_stride / width / height and **`duration_sec = frame_count / fps`** — β depends on this
   value.
7. Reads: `GET /runs/{id}/summary` and `/objects` parse **`tracks.csv`** from MinIO and apply β on
   the fly; `/timeline` parses `detections.csv`; `/overlay` returns `overlay.json`.
8. Rollup calls `get_summary` per completed shooting → **mean and median, plus std** across
   shootings, all three in one response (`MetricStat`); the UI toggle picks which centre to show.
   Two entry points, one code path: `/assignments/{id}/summary` (shootings of one assignment) and
   `/cities/{c}/routes/{r}/summary` (all shootings of the route). **The route averages shootings
   directly — there is no mean-of-means step**, so a two-drive campaign cannot outweigh a
   twenty-drive one; the route response also carries every shooting with its assignment. No
   shooting is ever filtered out of a rollup.
9. Route/city geometry lives in the DB (`routes.geometry`, `cities.roads_geometry`) and is served by
   `/cities/{c}/roads-geometry` and `/cities/{c}/routes/{r}/geometry` with weak `ETag`s. **The seeded
   cities and routes get their geometry from `0002_seed`**, which reads the nine geojson files in
   `apps/backend/alembic/seed_data/geometry/` and computes each city's bounds from its roads layer —
   so an empty database comes up with a working map and no manual step. New geometry arrives through
   `/admin` (upload recomputes the bounds in the same operation).
10. Frontend renders charts from `/summary`, `/objects`, `/timeline`, and the player from
   `/overlay` + `/playback`.

`brand_summary_by_tracks.csv`, `brand_summary_by_detections.csv`, `frame_summary.csv` are written and
registered but **nothing downstream reads them** — the backend recomputes from `tracks.csv`. They
only feed the pipeline's own `report.html`.

---

## 7. Change cookbook

| I need to… | Touch |
|---|---|
| Retune area/position/contrast/confidence numbers | `ScoringConfig` in [config.py](ml/pipeline/scripts/config.py) only |
| Change how a factor is computed | the one file in `ml/pipeline/scripts/scoring/`, plus its class in [tests/test_scoring.py](tests/test_scoring.py) |
| Add/remove a CSV column | `pipeline_contracts/artifacts.py` (field list is derived from the model) → the dataclass in `ml/pipeline/scripts/schemas.py` → whoever reads it |
| Change β semantics / zone model | `apps/backend/src/domain/geozones.py` + `_apply_beta` in `pipeline_run_service.py` + `RouteGeozone` model |
| Change how zones are entered or edited | `apps/frontend/src/components/RouteGeozones.tsx` — one panel for both mounts (city page without video, shooting card with it); percent↔fraction lives in `toFraction`/`percentText` there |
| Add an endpoint | router in `presentation/http/routers/v1/` → response DTO in `presentation/http/dto/response.py` → service → repository interface → SQL repository |
| Add a DB table/column | `infrastructure/database/models.py`, then **the owner writes the migration** (existing convention) |
| Change how an assignment **or a route** aggregates shootings | `application/services/metrics_rollup.py` — the only place that decides how shootings collapse (today: mean + median + std, no filtering), shared by both levels |
| Change which centre estimate the UI shows, or add a third one | `MetricStatDTO` → `_stat()` in `metrics_rollup.py` → `MetricStat` in `types.ts` → `statValue`/`formatStat` in `utils/formatters.ts` → `AggregateToggle.tsx`. The choice itself never reaches the backend |
| Add a city/route field, change geometry handling | `domain/geometry.py` (validation only) → `models.py` → `sql_catalog_repository` → `catalog_service` → `cities.py` router → `AdminPage.tsx`. Geometry must stay out of list responses |
| Change who can see hidden cities/routes | `include_inactive` threads through `list_cities` / `get_city` (repository → service → router → `api.ts`). Only `AdminPage.tsx` passes `true` |
| Change catalogue parsing (new column, new format) | `infrastructure/catalog/parser.py` only; the row/point types live in `domain/catalog.py` |
| Retune catalogue distance thresholds | `MERGE_DISTANCE_M` / `DIFF_DISTANCE_M` / `CITY_BOUNDS_MARGIN_M` in `domain/catalog.py` |
| Change how a catalogue pack is uploaded or a revision rolled back | `components/CatalogImports.tsx` (admin only). `CatalogPage.tsx` is the read-only directory and must stay that way |
| Add a section to the admin panel | a component under `components/`, mounted from `AdminPage.tsx`. City-scoped → a tab in `CITY_TABS`; not city-scoped → a page-level section in `AdminSection` (like `AdminUsers.tsx`). Keep the two switchers visually different — underlined text for sections, pill tabs inside a city — or they read as one level. Guard its writes with `require_admin` in the same change |
| Change the people directory | `user_service.py` → `users.py` router → `AdminUsers.tsx` — creation, renaming and hiding all live there. `UserSelect.tsx` only selects; do not put a create form back into it (see §10) |
| Change what the overlay card shows | `viewer/payload.py` + `OverlayObjectPayload` in `pipeline_contracts/artifacts.py` + `VideoOverlayPlayer.tsx` |

---

## 8. Commands

```bash
./scripts/dev.sh up          # postgres + minio + migrations + backend (docker) + worker (host)
./scripts/dev.sh down|logs
uv run pytest                # needs postgres up; creates/drops ad_pipeline_test
uv run pytest tests/test_scoring.py     # pure unit tests, no DB
uv run ruff check . && uv run mypy .
cd apps/frontend && pnpm dev && pnpm build && pnpm lint
./run_video_pipeline.sh path/to/video.mp4     # standalone ML run (GPU + weights required)
```

---

## 9. Conventions

* **Layering:** presentation → application (services/DTOs) → domain (pure) → infrastructure.
  Services never import FastAPI; domain imports nothing project-specific.
* **DTOs:** application DTOs in `application/common/dto/`, HTTP response models in
  `presentation/http/dto/response.py`. Some application DTOs subclass contract models directly
  (`RunObjectDTO(TrackCsvRow)`), which is intentional — the CSV *is* the contract.
* **Admin password:** one login/password pair from settings (`ADMIN_USERNAME` / `ADMIN_PASSWORD`,
  default `admin`/`admin`), checked by `presentation/http/security.py` over HTTP Basic. It is **not**
  authorization and there are no roles — it fences the admin panel off from colleagues who have no
  business there, inside a corporate network. The login form in the UI is convenience only; the
  guarantee is that the endpoints answer 401 on their own. What it guards:
  * `require_admin` — every write on cities and routes, all four catalogue-revision writes
    (upload / apply / restore / delete), and **both** writes on people (`POST /users`,
    `PATCH /users/{id}`);
  * `allow_hidden` — `include_inactive` on `GET /cities`, `GET /cities/{slug}` and `GET /users`.
  * **The line is the cost of a mistake, not the difficulty.** Administration is what changes a
    directory for everyone at once. Operational work — assignments, shootings, video upload,
    geozones — stays open, or the product becomes unusable. What stays open on the directory side
    is reads only: the catalogue list (a product screen) and `GET /users` (every upload form's
    dropdown reads it).
* **API envelope:** every success response is `{"data": …}` (`OkResponse[T]`). Errors are
  `{"detail": "<Russian sentence>"}` produced by handlers in `presentation/http/exception_handlers.py`.
  Domain errors are typed exceptions in `application/exceptions.py`, never raw `HTTPException`.
* **PATCH semantics:** request models expose `changed_fields()` so only keys the client actually sent
  are updated; validation re-checks the whole invariant against stored values.
* **DB naming:** table `things`, PK `things_id`, FK `<table>_id`, timestamps `created_at`/`updated_at`
  with server defaults. Soft delete via `is_active` where history matters. **Cities and routes have
  no delete at all** — `is_active` is an ordinary `PATCH` field meaning hide/show, and there is no
  `DELETE` verb on either. Anything that hides must also be un-hideable from somewhere, or it is a
  one-way door (see §10).
* **Repositories** own transactions but do not commit; services call `commit()`/`rollback()`.
* **Comments** explain *why*, in Russian, and are dense in this codebase — match that density and
  keep them truthful when you edit the code they describe.
* **Frontend:** no state library, no router library; `fetch` wrapper in `api.ts`, types mirrored by
  hand in `types.ts`. Keep them in sync with backend response DTOs manually.

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
* `run_video_pipeline.sh` appends `--brand-overrides` when `ml/pipeline/brand_overrides.csv` exists,
  but `run_pipeline.py` has no such argument. The file is absent today, so the script works by luck.
* α is derived from `final_brand_conf` only; the "brand stability across the track" input is a stub
  parameter (`detections` is accepted and ignored in `scoring/confidence.py`).
* An object that was never classified still gets α = 0.5 (the floor) and counts as `other`.
* β needs `duration_sec`; it exists only after `mark_completed`. Shootings without an assignment have
  no route → no zones → β = 1 everywhere.
* Geozone validation is split: bounds (`0 ≤ start < end ≤ 1`) in `catalog_service`, overlap detection
  in `sql_catalog_repository` under a route row lock (`GeozoneOverlapError` → HTTP 409).
* **`JSONB` needs `none_as_null=True`.** By default SQLAlchemy writes Python `None` into a JSONB
  column as the JSON literal `null`, so `IS NOT NULL` is true and "geometry not loaded" becomes
  indistinguishable from loaded. Both geometry columns declare `JSONB(none_as_null=True)`; any new
  nullable JSONB column must do the same.
* **Geometry never travels in a list response.** `cities.roads_geometry` is up to 1.5 MB. Every query
  that loads `City` or `Route` models carries `defer(...)` on those columns, and DTOs expose only
  `has_geometry` / `has_roads_geometry`. `_route_to_dto` takes the flag as an argument on purpose —
  reading `route.geometry` there would undo the deferral. Geometry has its own endpoints with `ETag`.
* **Uploading a city's road layer recomputes `bounds_*` in the same operation.** The catalogue parser
  uses that box to drop out-of-town points; a new layer with a stale box silently discards good rows.
* **`ShootingMetricsDTO` is the unit of account at every level.** Assignment and route both read it;
  nothing aggregates aggregates. A route summary therefore re-reads `tracks.csv` for every completed
  shooting on the route — that is why `RoutePage` refetches its summary only when the completed count
  changes, not on the 5 s assignment poll.
* **Hiding without a way back is a one-way door — the bug that cost every city at once.** Before
  28.07.2026 `DELETE /cities/{slug}` set `is_active = false`, the list filtered it out, the slug
  stayed taken and no endpoint could flip it back: the owner "deleted" three cities and could
  neither see nor recreate them. Now `is_active` is a plain `PATCH` field and the admin page — and
  only it — passes `include_inactive=true`. **Any future soft-hide must ship its un-hide in the same
  change, and the screen that can hide must be able to show.**
* **Hidden means gone everywhere, including direct URLs.** `get_city` and `get_route` return `None`
  for inactive rows unless `include_inactive` is set, so a bookmarked `/archive/kerch` gives 404.
  The two admin write paths (`update_route`, `set_route_geometry`) pass `include_inactive=True` on
  purpose — they answer about the very row they just hid, and a 404 there would read as a failure.
* **Both centre estimates ship in every rollup response; the choice is presentation-only.**
  `MetricStat` carries `mean`, `median` and `std` together — switching is a re-render, never a
  request, and the backend never learns which one is on screen. Consequence for the future DWH step:
  a snapshot must store **both**, or the toggle stops working for past periods.
* **Under median the brand shares do not add up to 100 %.** Median is not linear — the median of a
  sum is not the sum of medians. This is a property of the estimate, not a bug; the pie chart's copy
  says so out loud under median. It is also why `visibility_share` no longer exists in the API: the
  share depends on the selected estimate, so it is computed in `RollupCharts.tsx` where the selection
  lives. Do not put it back on the server.
* **σ is shown for both estimates on purpose.** It describes the sample of shootings — how far the
  drives spread apart — not the centre estimate, and "can I trust this number" is the same question
  either way.
* **No shooting is ever filtered out of a rollup, and that rests on an unchecked assumption**: the
  video covers the whole drive from A to B. A truncated upload is invisible to the system — the zones
  simply shift, because β is a fraction of *this* video's duration, and the numbers go quietly wrong.
  Rejected deliberately (owner: every drive is uploaded whole); if the assumption ever breaks,
  filtering belongs in `metrics_rollup.py` and nowhere else.
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
