# Исправления к MVP-пайплайну анализа наружной рекламы

Текущий пайплайн хороший как база, но его нужно доработать по четырем важным направлениям:

1. Разделить detection crop и classification crop.
2. Добавить quality gate до классификатора, чтобы не отдавать в classifier crop-ы, которые плохо подходят для классификации по качеству текущего видео.
3. Добавить tracking/aggregation, чтобы понимать, что один и тот же билборд виден на разных кадрах.
4. Добавить систему score-ов: detection score, crop quality score, brand score, video visibility score, overall score.

## 1. Важное уточнение по сущностям

В пайплайне должны быть разные уровни данных:

```text
Frame
  -> Detection
      -> Crop
          -> Classification attempt
  -> Track/Object
      -> aggregated detections
      -> best crops
      -> final brand
      -> visibility metrics
```

Одна строка `detections.csv` — это одна детекция на одном кадре.

Но для бизнесовой аналитики нужна сущность выше:

```text
track_id / object_id
```

То есть один и тот же билборд, найденный на 30 кадрах подряд, должен считаться как один объект, а не как 30 разных билбордов.

## 2. Detection и classification — разные задачи

YOLO detector отвечает только на вопрос:

```text
Где рекламная поверхность?
```

Brand classifier отвечает на вопрос:

```text
Какой бренд на crop-е?
```

Visibility module отвечает на вопрос:

```text
Насколько рекламный объект заметен в данном видео/на маршруте?
```

Нельзя считать, что если YOLO нашла bbox, то этот bbox автоматически пригоден для классификации бренда. Если объект маленький, смазанный или плохо сохранен в доступном видео, classifier может быть ненадежен.

Важно: пайплайн не должен утверждать, что рекламу нельзя прочитать в реальности. Он может утверждать только, что по данному crop-у из данного видео бренд не был надежно классифицирован.

## 3. Crop нужно сохранять, но не каждый crop классифицировать

Для каждой принятой детекции нужно сохранить crop в любом случае, чтобы потом можно было проверить работу пайплайна.

Но перед classifier-ом должен быть отдельный classification gate.

Пример:

```text
YOLO нашла билборд
  -> crop сохраняем всегда
  -> если crop плохо подходит для classifier по текущему видео, classifier не запускаем
  -> classification_input_status = rejected
  -> brand_status = not_classified
  -> status_reason = small_crop_in_video / motion_blur_in_video / low_video_quality
```

## 4. Разделить пороги detection и classification

Сейчас в черновике указано:

```text
min_crop_width: 32 px
min_crop_height: 32 px
```

Это может быть допустимо для сохранения детекции, но не для классификации бренда.

Нужно ввести два набора порогов.

### Detection gate

Используется, чтобы понять, сохраняем ли детекцию вообще.

Черновые пороги:

```text
detector_conf_min: 0.25-0.35
min_detection_width: 32 px
min_detection_height: 32 px
min_bbox_area_ratio: 0.0005-0.001
```

### Classification gate

Используется, чтобы понять, стоит ли отправлять crop в classifier.

Это не оценка реальной читаемости рекламы человеком. Это техническая оценка пригодности конкретного crop-а из конкретного видео как входа для classifier.

Черновые пороги:

```text
min_classify_width: 120 px
min_classify_height: 60 px
min_classify_area_ratio: 0.002-0.005
```

Если crop меньше этих значений:

```text
crop_quality_status = rejected
crop_quality_reason = too_small_for_classification
classification_input_status = rejected
classification_attempted = false
brand_status = not_classified
brand = null
```

Важно: конкретные значения нужно подобрать после просмотра первых реальных crop-ов.

## 5. Quality gate должен возвращать не только status, но и crop_quality_score

Quality gate должен возвращать:

```text
crop_quality_status:
  passed
  borderline
  rejected

crop_quality_reason:
  ok
  too_small_for_classification
  small_crop_in_video
  motion_blur_in_video
  low_video_quality
  too_dark_in_video
  too_bright_in_video
  low_detector_conf
  bad_aspect_ratio
  clipped_by_frame_border

crop_quality_score:
  float 0.0-1.0
```

Пример логики:

```text
crop достаточно крупный, не смазан, нормальная яркость:
  crop_quality_status = passed
  crop_quality_score = 0.85-1.0

crop неидеальный, но classifier все еще может дать полезный сигнал:
  crop_quality_status = borderline
  crop_quality_score = 0.45-0.75

crop слишком мелкий/смазанный:
  crop_quality_status = rejected
  crop_quality_score = 0.0-0.45
```

Если `crop_quality_status = rejected`, classifier не запускаем.

Если `crop_quality_status = borderline`, classifier можно запустить, но финальный статус почти всегда должен быть `manual_review`, кроме случаев очень высокой уверенности.

Не используем формулировки вроде `unreadable` как финальный вывод. Безопаснее писать: `not_classified` с причиной `small_crop_in_video`, `motion_blur_in_video` или `low_video_quality`.

## 6. Нужно выбирать лучший crop по объекту, а не классифицировать каждый кадр одинаково

Для видео один и тот же рекламный объект может быть виден на разных кадрах:

```text
frame 100: далеко, crop маленький
frame 110: ближе, crop лучше
frame 120: лучший кадр
frame 130: объект уходит из кадра
```

Правильная логика:

```text
1. YOLO находит detections.
2. Detections объединяются в track/object.
3. По каждому track выбираются лучшие crop-ы.
4. Classifier запускается на best crops.
5. Итоговый бренд считается по нескольким лучшим crop-ам.
```

Для MVP можно начать с простой логики:

```text
для каждого track выбрать top-N crop-ов по crop_quality_score * area_ratio * det_conf
```

Например:

```text
best_crops_per_track: 3 или 5
```

Только эти crop-ы отправлять в classifier.

## 7. Tracking / aggregation нужен для подсчета видимости

В первой версии можно реализовать простую IoU-агрегацию между соседними обработанными кадрами.

Пример:

```text
если detection на frame N и detection на frame N+stride имеют IoU >= 0.3-0.5,
считать их одним track_id
```

Поля track:

```text
track_id
source_path
first_frame_index
last_frame_index
first_timestamp_sec
last_timestamp_sec
detections_count
best_crop_path
best_crop_quality_score
max_area_ratio
mean_area_ratio
mean_video_visibility_score
final_brand
final_brand_conf
final_status
```

Важно: для MVP `track_id` означает “один объект внутри одного видео/прохода”. Это не глобальный ID билборда в реальном мире. Чтобы понимать, что это тот же самый физический билборд в разные дни/маршруты, позже понадобятся GPS, геопривязка, re-identification или ручная связка.

## 8. Как считать видимость в видео

Нужно не просто определить бренд, но и посчитать, насколько рекламная поверхность была заметна в данном видео/на данном маршруте.

Это не абсолютная видимость объекта в реальном мире. На результат влияют камера, битрейт, погода, освещение, угол, скорость движения и качество исходного видео.

Для каждой detection считаем:

```text
area_ratio = bbox_area / frame_area
center_x_norm = bbox_center_x / frame_width
center_y_norm = bbox_center_y / frame_height
position_label = left/top, right-middle и т.д.
```

Дополнительно нужно посчитать `position_weight`.

Пример простой логики:

```text
объект ближе к центру кадра -> position_weight выше
объект на краю кадра -> position_weight ниже
```

Черновая логика:

```text
center_distance = distance from frame center, normalized 0..1
position_weight = 1.0 - center_distance
position_weight clipped to 0.2..1.0
```

Потом считаем frame-level visibility:

```text
geometry_visibility_score = area_score * position_weight
```

Где:

```text
area_score = normalized area_ratio
position_weight = вес позиции объекта в кадре
```

Для MVP можно считать:

```text
video_visibility_score = geometry_visibility_score
```

Позже можно добавить отдельный `detection_reliability_weight`, если нужно ослаблять вклад слабых/сомнительных detections:

```text
video_visibility_score = geometry_visibility_score * detection_reliability_weight
```

Важно: `crop_quality_score` не должен автоматически умножаться на visibility. Плохой crop может мешать classifier-у, но рекламная поверхность все равно могла быть заметна в видео.

Чтобы метрика не зависела напрямую от `frame_stride`, добавляем временной вес:

```text
video_visibility_weighted_seconds = video_visibility_score * delta_t_sec
```

По track считаем:

```text
track_video_visibility_score = sum или mean video_visibility_score по detections track-а
track_video_visibility_weighted_seconds = sum video_visibility_weighted_seconds
track_visible_duration_sec = last_timestamp_sec - first_timestamp_sec
track_max_area_ratio = max(area_ratio)
track_mean_area_ratio = mean(area_ratio)
```

Для отчета полезно иметь две метрики:

```text
object_count_visibility:
  сколько уникальных рекламных объектов найдено по брендам

exposure_visibility:
  сколько времени/кадров бренд был виден и с какой площадью
```

## 9. Добавить overall score

Нужно считать не один score, а несколько:

```text
det_score        — уверенность YOLO detector
crop_quality_score — насколько crop пригоден как вход для classifier
brand_score      — уверенность classifier
video_visibility_score — насколько рекламная поверхность заметна в данном видео
overall_score    — общий score для карточки/отчета
```

### Per-detection overall_score

Для одной детекции:

```text
overall_score = 
  0.30 * det_conf +
  0.30 * crop_quality_score +
  0.25 * brand_conf +
  0.15 * video_visibility_score_norm
```

Если classifier не запускался:

```text
brand_conf = 0
overall_score = 
  0.40 * det_conf +
  0.40 * crop_quality_score +
  0.20 * video_visibility_score_norm
```

### Per-track final_score

Для объекта/track:

```text
track_final_score =
  0.30 * mean_det_conf +
  0.25 * best_crop_quality_score +
  0.25 * final_brand_conf +
  0.20 * track_video_visibility_score_norm
```

Значения весов на MVP можно оставить конфигурируемыми.

`overall_score` — это технический score доверия к карточке/результату пайплайна. Его не нужно использовать как замену `video_visibility_score`.

## 10. Финальный бренд нужно считать по track, а не только по одной detection

Если classifier запускается на нескольких best crop-ах одного track-а, нужно агрегировать предсказания.

Пример:

```text
crop_1: mts 0.82
crop_2: mts 0.76
crop_3: miranda 0.51
```

Итог:

```text
final_brand = mts
final_brand_conf = средняя/максимальная уверенность по mts
final_status = detected_brand или manual_review
```

Если предсказания конфликтуют:

```text
crop_1: mts 0.72
crop_2: miranda 0.70
crop_3: plus7 0.66
```

Итог:

```text
final_status = manual_review
final_brand = null или наиболее вероятный бренд с пометкой conflict
status_reason = brand_conflict_across_track
```

## 11. Обновить статусы

Текущие статусы нормальные, но их нужно разделить по слоям, чтобы не смешивать качество видео, классификацию бренда и бизнесовый статус.

```text
crop_quality_status:
  passed
  borderline
  rejected

classification_input_status:
  accepted
  borderline
  rejected

brand_status:
  detected_brand
  other
  unknown
  manual_review
  not_classified

final_status:
  detected_brand
  other
  unknown
  manual_review
  not_classified
```

Причину нужно хранить отдельно:

```text
crop_quality_reason:
  ok
  too_small_for_classification
  small_crop_in_video
  motion_blur_in_video
  low_video_quality
  too_dark_in_video
  too_bright_in_video
  low_detector_conf
  bad_aspect_ratio
  clipped_by_frame_border
```

Для бизнес-отчета важно разделять:

```text
unknown — модель не уверена
not_classified — classifier не запускался или результат не принят из-за качества crop-а в текущем видео
manual_review — можно проверить человеком
other — реклама не из целевых телеком-брендов
```

В отчете нельзя писать “бренд невозможно прочитать”. Безопасная формулировка:

```text
бренд не был надежно определен по доступному видеоматериалу
```

## 12. Обновить detections.csv

Добавить поля:

```text
run_id
source_path
input_type
frame_index
timestamp_sec
det_index
track_id

det_class
det_conf

bbox_x1
bbox_y1
bbox_x2
bbox_y2
bbox_width
bbox_height
bbox_area
area_ratio

center_x
center_y
center_x_norm
center_y_norm
position_label
position_weight

crop_path
crop_width
crop_height

crop_quality_status
crop_quality_reason
crop_quality_score
classification_input_status

classification_attempted
brand_pred
brand_conf
top1_brand
top1_score
top2_brand
top2_score
top3_brand
top3_score

video_visibility_score
video_visibility_weighted_seconds
overall_score

brand_status
final_status
status_reason
```

## 13. Добавить tracks.csv

Нужна отдельная таблица по уникальным объектам.

```text
tracks.csv
```

Колонки:

```text
run_id
source_path
track_id

first_frame_index
last_frame_index
first_timestamp_sec
last_timestamp_sec
visible_duration_sec

detections_count
classified_crops_count

best_crop_path
best_frame_index
best_timestamp_sec

mean_det_conf
max_det_conf

mean_crop_quality_score
best_crop_quality_score

max_area_ratio
mean_area_ratio
sum_area_ratio

mean_position_weight
mean_video_visibility_score
sum_video_visibility_score
video_visibility_weighted_seconds

final_brand
final_brand_conf
final_status
final_status_reason

track_final_score
manual_review_required
```

Именно `tracks.csv` должен использоваться для подсчета количества уникальных рекламных объектов.

`detections.csv` нужен для отладки покадровой работы.

## 14. Обновить brand_summary.csv

Агрегацию по брендам лучше строить не только по detections, но и по tracks.

Добавить две версии:

```text
brand_summary_by_detections.csv
brand_summary_by_tracks.csv
```

В `brand_summary_by_tracks.csv`:

```text
brand
status
track_count
mean_track_final_score
mean_video_visibility_score
sum_video_visibility_score
video_visibility_weighted_seconds
mean_final_brand_conf
max_final_brand_conf
first_timestamp_sec
last_timestamp_sec
```

## 15. Обновить графики

Нужны не только графики по брендам, но и графики по visibility/score.

Минимальный набор:

```text
charts/
  detections_by_brand.png
  tracks_by_brand.png
  status_counts.png
  confidence_distribution.png
  crop_quality_score_distribution.png
  video_visibility_by_brand.png
  video_visibility_timeline.png
  area_ratio_timeline.png
  manual_review_cases.png
```

### video_visibility_timeline

По X:

```text
timestamp_sec
```

По Y:

```text
sum video_visibility_score по кадру
```

Группировка:

```text
brand/status
```

### video_visibility_by_brand

По брендам:

```text
sum_video_visibility_score
mean_video_visibility_score
video_visibility_weighted_seconds
track_count
```

## 16. Обновить визуализацию на видео

На annotated video рядом с bbox нужно показывать карточку:

```text
Brand: MTS
Status: detected_brand
Det: 0.87
Cls: 0.82
CropQ: 0.74
Area: 2.1%
VideoVis: 0.63
Score: 0.79
Track: 12
```

Если crop не классифицировался:

```text
Status: not_classified
Reason: small_crop_in_video
Det: 0.71
CropQ: 0.22
Area: 0.1%
Track: 8
```

Важно: если объект `manual_review`, `unknown` или `not_classified`, нельзя рисовать карточку так, будто бренд подтвержден.

## 17. Обновить HTML report

В отчете нужно разделить:

### 1. Detection summary

```text
сколько рекламных поверхностей найдено покадрово
```

### 2. Track/object summary

```text
сколько уникальных рекламных объектов найдено
```

### 3. Brand summary

```text
сколько объектов каждого бренда
```

### 4. Visibility summary

```text
видимость по брендам:
- track_count
- sum_video_visibility_score
- mean_video_visibility_score
- video_visibility_weighted_seconds
- max_area_ratio
- visible_duration_sec
```

### 5. Quality summary

```text
сколько объектов не удалось классифицировать из-за:
- too_small_for_classification
- small_crop_in_video
- motion_blur_in_video
- low_video_quality
- low_confidence
```

### 6. Manual review gallery

```text
crop-ы, которые нужно проверить руками
```

Приоритет ручной проверки:

```text
high video_visibility_score + low brand_conf
high video_visibility_score + brand_conflict_across_track
high video_visibility_score + not_classified
```

### 7. Best detections gallery

```text
лучшие crop-ы по track_final_score
```

## 18. Обновить порядок реализации

Правильный порядок реализации MVP:

```text
1. Image pipeline:
   image -> detector -> crops -> detections.csv -> annotated image

2. Video sampling:
   video -> sampled frames -> detector -> detections.csv -> crops

3. Quality gate:
   crop_quality_status, crop_quality_reason, crop_quality_score

4. Classification:
   запускать classifier только для passed/borderline crop-ов

5. Scoring:
   det_score, crop_quality_score, brand_score, video_visibility_score, overall_score

6. Simple tracking:
   detections -> track_id через IoU на соседних кадрах

7. Track aggregation:
   best crops, final_brand, final_status, track_final_score

8. Reports:
   detections.csv, tracks.csv, summaries

9. Visualization:
   annotated frames/video с карточками

10. Charts + HTML report
```

## 19. Конфиг MVP

Добавить конфиг:

```text
frame_stride: 5

detector_conf_min: 0.30
min_detection_width: 32
min_detection_height: 32
min_detection_area_ratio: 0.0005

min_classify_width: 120
min_classify_height: 60
min_classify_area_ratio: 0.002

crop_margin_ratio: 0.05

crop_quality_pass_min: 0.65
crop_quality_borderline_min: 0.40

brand_conf_accept: 0.80
other_conf_accept: 0.85
manual_review_min: 0.50

tracking_iou_min: 0.35
max_track_gap_frames: 2
best_crops_per_track: 3
```

Все значения должны быть вынесены в config и легко меняться.

## 20. Главное изменение в понимании результата

Для бизнес-метрик использовать не `detections.csv`, а `tracks.csv`.

`detections.csv` отвечает на вопрос:

```text
Что модель увидела на каждом кадре?
```

`tracks.csv` отвечает на вопрос:

```text
Какие уникальные рекламные объекты были на маршруте?
```

`brand_summary_by_tracks.csv` отвечает на вопрос:

```text
Сколько уникальных объектов каждого бренда было найдено?
```

`video_visibility_by_brand` отвечает на вопрос:

```text
Насколько каждый бренд был заметен в данном видео/на данном маршруте?
```

Это ключевая поправка к пайплайну.
