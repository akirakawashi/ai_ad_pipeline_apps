# План реализации новой метрики заметности

Рабочий пошаговый план для реализации. Исполняется **по шагам, сверху вниз**. Каждый шаг оставляет пайплайн в рабочем (зелёном) состоянии.

- **Что считаем и почему** — см. [visibility-score-methodology.md](visibility-score-methodology.md) (методика для бизнеса).
- **Общая стратегия и карта кода** — здесь, ниже.
- **Прогресс** — чеклист в конце файла, отмечать по мере выполнения.

---

## Стратегия: старую убираем сразу, новую строим по шагам

Старая метрика **не в проде** и **не одобрена бизнесом** — заведомо неправильная логика. Держать её как эталон или ориентир смысла нет: равняться не на что. Классический «strangler» (строить рядом с живой системой) здесь не нужен — он для прод-систем, которые нельзя ронять. У нас проще:

1. **Старую метрику удаляем в самом начале (Шаг 0)** — сразу вместе с каркасом нового модуля и переводом контракта на новые поля. Никаких двойных наборов полей и переключателей.
2. **Новую логику пишем в новом модуле** `scoring/`, по одному фактору за шаг. Инкрементальность — чтобы управлять сложностью, а не чтобы беречь старое.
3. **Пайплайн держим рабочим заглушками:** после Шага 0 он гоняется и пишет новые поля (пока плейсхолдеры), которые становятся реальными по мере шагов. Это не «ориентир на старое» — это чтобы не строить вслепую.
4. **Downstream (бэкенд/DTO/фронт) переводим на новое поле, когда числа уже реальные (Шаг 7).** Прода нет — не страшно, что на ветке бэкенд/фронт временно показывают плейсхолдер, пока строим факторы.

> Что «красное» во время сборки: только показ в бэкенде/фронте (не прод). Сам пайплайн зелёный с Шага 0.

---

## Карта текущего кода

### Стадии пайплайна ([runner.py](ml/pipeline/scripts/runner.py))
```
run_detection_stage        детекция + кропы + качество (per-frame, стримингом для видео)
run_tracking_stage         assign_track_ids → build_tracks → assign_object_groups
run_classification_stage   classify_detections
run_final_aggregation_stage build_tracks + apply_track_results   ← ЗДЕСЬ скоринг
run_business_rules_stage   stabilize_object_brands
write_artifacts_stage      кропы, annotated media, viewer, CSV (write_pipeline_outputs)
```

### Слой метрики — ПОД ЗАМЕНУ
| Файл | Что заменяем |
|---|---|
| [visibility.py](ml/pipeline/scripts/visibility.py) | `fill_geometry_fields` (скоринговая часть: `area_score`, `position_weight`, `video_visibility_score`, `video_visibility_weighted_seconds`), `position_weight`, `position_label`. **Геометрию** (`center_x`, `center_x_norm` …) — оставить, она инфраструктурная |
| [aggregation.py](ml/pipeline/scripts/aggregation.py) | `track_final_score` (в `_aggregate_one`), `compute_detection_overall_score`, `_best_detection_score`, visibility-агрегации (`mean/sum_video_visibility_score`, `video_visibility_weighted_seconds`, `mean_position_weight`) |
| [config.py](ml/pipeline/scripts/config.py) | `VisibilityConfig` (`area_norm`, `min_position_weight`) |

### Инфраструктура — ОСТАЁТСЯ (переиспользуем)
detection.py, crops.py, quality.py, classification.py, tracking.py, track_groups.py, io.py; в aggregation.py — `build_tracks` (каркас), `_aggregate_brand` (голосование по бренду → кормит уверенность), `visible_duration_sec` (**время!**), `_is_track_confirmed`, `_track_object_id`, `_business_brand`.

### Downstream — потребители метрики (перевести на новое поле, Шаг 7)
- Бэкенд: [pipeline_run_service.py](apps/backend/src/application/services/pipeline_run_service.py) (`visibility_index` из `video_visibility_weighted_seconds`; сортировка объектов), [measurement_rollup.py](apps/backend/src/application/services/measurement_rollup.py)
- DTO: [catalog.py](apps/backend/src/application/common/dto/catalog.py) (`BrandSummaryDTO`, `RunObjectDTO`, `MeasurementPassDTO` …)
- CSV: [reporting/summaries.py](ml/pipeline/scripts/reporting/summaries.py), поля в [artifacts.py](ml/pipeline/scripts/artifacts.py)
- Фронт: `MeasurementCharts.tsx`, `RunCharts.tsx`

> Точный список потребителей подтвердить перед Шагом 7:
> `grep -rn "video_visibility_weighted_seconds\|visibility_index\|track_final_score\|overall_score" apps/`

---

## Целевая архитектура

### Формулы (из методички)
```
Интенсивность (кадр k):   I_k = A_k · P_k · C_k
Секунды внимания (объект): S  = Σ_k ( I_k · Δt_k )
Итоговый балл (объект):    V  = S · α · β
```
`A` — площадь, `P` — положение+сторона, `C` — контраст (все 0…1); `Δt_k` = `sample_delta_t_sec`; `α` — уверенность (0.5…1), `β` — значимость (Фаза 2, пока = 1).

### Новый модуль `ml/pipeline/scripts/scoring/`
```
area.py          area_ratio            → A   (тир-таблица + интерполяция)
position.py      center_x/y + сторона  → P   (зоны своя/встречная × центр/средняя/периферия)
contrast.py      кроп vs кольцо фона    → C   (НОВЫЙ CV-шаг)
intensity.py     I = A · P · C                (на детекцию)
attention.py     S = Σ I·Δt                   (на объект)
confidence.py    brand_conf + стабильность → α
significance.py  координаты → β               (Фаза 2; пока заглушка = 1.0)
combiner.py      V = S · α · β
```
Принцип: **извлечение признаков (area/position/contrast/…) отдельно от сборки (combiner).** Числа-таблицы — в конфиге, бизнес тюнит без правки кода.

### Новые поля на записях ([schemas.py](ml/pipeline/scripts/schemas.py)) — вместо старых
- `DetectionRecord`: `area_coef`, `position_coef`, `contrast_coef`, `intensity`
- `TrackRecord` (объект): `attention_seconds` (S), `confidence_coef` (α), `significance_coef` (β), `visibility_value` (V)

### Новый конфиг `ScoringConfig`
`area_table`, `position_table`, `contrast` (пороги + что считать фоном), `confidence_table`, `handedness` (право/лево-стороннее), `significance` (Фаза 2).

---

## Дефолты и открытые развилки

Чтобы не блокироваться до ТЗ — ставим дефолты, бизнес тюнит потом.

| Развилка | Дефолт на старте |
|---|---|
| Таблица площади | `<0.5% → 0.30`, `0.5–2% → 0.70`, `2–5% → 1.0` (интерполяция между точками) |
| Таблица положения | своя-центр `1.0`, своя-средняя `0.85`, своя-периферия `0.70`, встречная-центр `0.60`, встречная-периферия `0.50` |
| Контраст: что фон | кольцо вокруг bbox; метрика — контраст по яркости; пороги low `0.60` / mid `0.80` / high `1.0` |
| Таблица уверенности | `>0.90 → 1.0`, `0.80–0.90 → 0.9`, ниже — линейно к полу `0.5` |
| Значимость (β) | `1.0` (Фаза 1, гео нет) |
| Сторонность | правостороннее движение |
| Нормировка «процента» | отложена; на показе — доля внутри видео. На расчёт `V` не влияет |
| Интерполяция | линейная между тирами (не ступеньки), для непрерывных: площадь, контраст, уверенность |

---

## Пошаговый план — Фаза 1 (только видео)

Шаблон каждого шага: **Цель · Файлы · Поля/конфиг · Куда встраивается · Проверка · Готово · Коммит.**

### Шаг 0 — Снос старого + каркас нового
- **Цель:** старая метрика удалена, на её месте модуль-заглушка, пайплайн зелёный на плейсхолдерах.
- **Разведка (подтвердить перед кодом):** где вызывается `fill_geometry_fields` (call-site геометрии на детекцию); определения CSV-полей в [artifacts.py](ml/pipeline/scripts/artifacts.py); список downstream-потребителей (grep выше).
- **Удалить:** скоринг из [visibility.py](ml/pipeline/scripts/visibility.py) (`video_visibility_score`, `video_visibility_weighted_seconds`, `position_weight`, `position_label` — геометрию `center_x/_norm` оставить); из [aggregation.py](ml/pipeline/scripts/aggregation.py) — `track_final_score`, `compute_detection_overall_score`, `_best_detection_score`, visibility-агрегации; `VisibilityConfig`; старые поля из `schemas.py` и CSV-контракта ([artifacts.py](ml/pipeline/scripts/artifacts.py)).
- **Создать:** пакет `scoring/` с заглушками (каждый фактор → `1.0`); `ScoringConfig`; новые поля на записях + новые CSV-колонки; вызов `combiner` в `run_final_aggregation_stage`.
- **Проверка:** `./run_video_pipeline.sh` → пайплайн зелёный, в CSV новые колонки (плейсхолдеры); `grep -rn "video_visibility\|track_final_score\|overall_score\|VisibilityConfig" ml/` — пусто.
- **Готово:** старой метрики в пайплайне нет; прогон без ошибок; новые поля на месте (бэкенд/фронт чиним на Шаге 7).
- **Коммит:** `refactor(scoring): удалить старую метрику, поставить каркас новой`

### Шаг 1 — Площадь → A
- **Цель:** `area_coef` из `area_ratio` по тир-таблице с интерполяцией.
- **Файлы:** `scoring/area.py`; `ScoringConfig.area_table` (дефолт выше).
- **Куда встраивается:** per-detection, на стадии детекции (рядом с геометрией).
- **Проверка:** юнит-тест интерполяции на границах бинов; мелкий щит → низкий `A`, крупный → высокий; монотонность.
- **Готово:** `area_coef` заполнен, гладкий, без обрывов.
- **Коммит:** `feat(scoring): коэффициент площади (тиры + интерполяция)`

### Шаг 2 — Положение + сторона → P
- **Цель:** `position_coef` из положения в кадре и стороны дороги (v1).
- **Файлы:** `scoring/position.py`; `ScoringConfig.position_table`, `handedness`.
- **Логика v1:** сторона по `center_x_norm` + флаг `handedness` (без GPS). Зоны: своя/встречная × центр/средняя/периферия.
- **Куда встраивается:** per-detection; переиспользует геометрию (`center_x_norm`, `center_y_norm`).
- **Проверка:** юнит-тесты маппинга зон; асимметрия лево/право (встречка весит меньше).
- **Готово:** `position_coef` заполнен, встречная сторона < попутной.
- **Коммит:** `feat(scoring): коэффициент положения со стороной движения (v1, экран-X)`

### Шаг 3 — Контраст → C (новый CV)
- **Цель:** `contrast_coef` из контраста рекламы к фону.
- **Файлы:** `scoring/contrast.py`; `ScoringConfig.contrast` (пороги + определение фона).
- **Логика:** яркость/цвет региона щита vs кольцо фона вокруг bbox → метрика контраста → коэффициент по порогам. Нужен доступ к пикселям кадра (как в [quality.py](ml/pipeline/scripts/quality.py)).
- **Куда встраивается:** per-detection, на стадии детекции (там есть кадр и bbox).
- **Проверка:** визуальный спот-чек на кропах (яркий щит → высокий `C`, сливающийся → низкий); юнит на синтетике.
- **Готово:** `contrast_coef` заполнен и осмыслен.
- **Коммит:** `feat(scoring): коэффициент контраста к фону`

### Шаг 4 — Интенсивность и интегратор → S
- **Цель:** `intensity = A·P·C` на детекцию; `attention_seconds = Σ intensity·Δt` на объект.
- **Файлы:** `scoring/intensity.py`, `scoring/attention.py`.
- **Куда встраивается:** `intensity` — per-detection; `attention_seconds` — в `run_final_aggregation_stage` (агрегация по объекту, `Δt = sample_delta_t_sec`).
- **Проверка:** ручной расчёт на маленьком примере совпадает; `S ≤ visible_duration_sec`; пример из методички (8 кадров → 0.50).
- **Готово:** `attention_seconds` заполнен, сходится с ручным счётом.
- **Коммит:** `feat(scoring): секунды внимания (интеграл интенсивности по времени)`

### Шаг 5 — Уверенность → α
- **Цель:** `confidence_coef` из уверенности бренда + стабильности по треку.
- **Файлы:** `scoring/confidence.py`; `ScoringConfig.confidence_table`.
- **Логика:** берём выход `_aggregate_brand` (`final_brand_conf`) + согласованность голосов по кадрам (стабильность) → α ∈ [0.5, 1].
- **Куда встраивается:** `run_final_aggregation_stage` / после голосования по бренду.
- **Проверка:** стабильные высокие → ~1.0; «мигающий» бренд → ниже, но ≥ 0.5.
- **Готово:** `confidence_coef` заполнен в диапазоне.
- **Коммит:** `feat(scoring): коэффициент уверенности (величина + стабильность)`

### Шаг 6 — Комбайнер → V
- **Цель:** `visibility_value = attention_seconds · α · β` (β = 1.0, заглушка значимости).
- **Файлы:** `scoring/combiner.py`, `scoring/significance.py` (заглушка).
- **Куда встраивается:** конец `run_final_aggregation_stage`, когда S/α/β известны.
- **Проверка:** `V = S·α` (β=1); прогон на видео; sanity глазами — самые заметные щиты набирают больший `V`. Старую метрику эталоном не берём (не одобрена).
- **Готово:** `visibility_value` заполнен; sanity-проверка пройдена.
- **Коммит:** `feat(scoring): комбайнер итогового балла V = S·α·β`

### Шаг 7 — Проводка downstream на новую метрику
- **Цель:** бэкенд/DTO/фронт читают `visibility_value` (уже реальный) — всё приложение на новой метрике.
- **Файлы:** [pipeline_run_service.py](apps/backend/src/application/services/pipeline_run_service.py) (`visibility_index` → сумма `visibility_value`; сортировка объектов), DTO [catalog.py](apps/backend/src/application/common/dto/catalog.py), фронт `MeasurementCharts.tsx`/`RunCharts.tsx`. (CSV-контракт уже на новых полях — с Шага 0.)
- **Проверка:** приложение целиком поднимается; графики показывают новую метрику; значения вменяемы.
- **Готово:** весь стек на новой метрике. Старой в коде нет с Шага 0.
- **Коммит:** `feat: провести бэкенд и фронт на новую метрику заметности`

---

## Фаза 2 — Гео (позже, нужны внешние данные)

Не начинать, пока нет: **GPS-трека к видео** и **источника данных трафика**.

- **Шаг 8 — Контракт входа:** run = видео + GPS-трек (lat/lon/heading/время) + метаданные; `FrameRecord` получает `(lat, lon, heading)`; синхронизация GPS↔видео (**линчпин** — часы, интерполяция, выпадения; нужен QA).
- **Шаг 9 — Значимость β:** `significance.py` по-настоящему — провайдер «координата → коэффициент» на слое данных трафика. Применять предпочтительно **в rollup на бэкенде** (там уже геометрия `Route.geojson`), а не в тяжёлом ML-прогоне.
- **Шаг 10 — Сторона v2:** истинный азимут щита из heading (точнее экран-X из Шага 2).

---

## Прогресс

- [x] Шаг 0 — Снос старого + каркас нового
- [x] Шаг 1 — Площадь → A
- [x] Шаг 2 — Положение + сторона → P
- [x] Шаг 3 — Контраст → C
- [x] Шаг 4 — Интегратор → S (сделан в каркасе Шага 0)
- [x] Шаг 5 — Уверенность → α
- [x] Шаг 6 — Комбайнер → V (сделан в каркасе Шага 0)
- [x] Шаг 7 — Проводка downstream на новую метрику
- [ ] Фаза 2: Шаг 8 — Контракт входа (GPS)
- [ ] Фаза 2: Шаг 9 — Значимость β
- [ ] Фаза 2: Шаг 10 — Сторона v2

---

## Открытые вопросы к ТЗ бизнеса (не блокируют старт)

1. Финальные числа таблиц (площадь / положение / контраст / уверенность) — сейчас на дефолтах.
2. Источник данных трафика для значимости (Фаза 2).
3. «Процент заметности» — доля внутри видео или абсолютная шкала (шаг показа, не расчёта).
4. Что считать «фоном» для контраста — сейчас дефолт «кольцо вокруг щита».
