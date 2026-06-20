# MVP Pipeline: Outdoor Ad Visibility Analysis

Technical spec for the local end-to-end pipeline without frontend/backend.

## Scope

Build a local pipeline that takes one video or image, detects outdoor advertising surfaces, crops detections, classifies brands on selected crops, aggregates detections into route-level objects/tracks, and produces visibility-oriented outputs.

Current models:

- detector: YOLO ad surface detector;
- classifier: brand classifier with classes `mts`, `plus7`, `miranda`, `other`.

Frontend, backend, MinIO, auth, and job queues are out of scope for this MVP step.

## Input Location

Put local test inputs here:

```text
ml/data/pipeline/input/
  videos/
  images/
```

This directory is for local pipeline experiments. It is different from future app uploads, which should later come from MinIO/backend job storage.

## Core Assumption

For MVP:

```text
1 video = 1 route / 1 pass
```

The pipeline should count all advertising objects found on that route.

`track_id` / `object_id` means one advertising object inside one video/route. It is not a global real-world billboard ID. Linking the same physical billboard across different days/routes will later require GPS, georeferencing, re-identification, or manual mapping.

## Data Levels

The pipeline must keep separate data levels:

```text
Run / Route
  -> Frame
      -> Detection
          -> Crop
          -> Classification attempt
  -> Track/Object
      -> aggregated detections
      -> best crops
      -> final brand
      -> video visibility metrics
```

One row in `detections.csv` is one detection on one sampled frame.

Business analytics must use `tracks.csv`, because one ad object can be visible across many frames and should not be counted as many separate billboards.

## Responsibilities

YOLO detector answers:

```text
Where is an advertising surface?
```

Brand classifier answers:

```text
Which brand is visible on this crop?
```

Video visibility module answers:

```text
How noticeable was this advertising object in this video/route?
```

The pipeline must not claim that an ad is unreadable in the real world. It can only claim that the brand was not reliably classified from the available crop/video material.

## High-Level Flow

```text
video/image
  -> frame loader
  -> YOLO detector
  -> detection gate
  -> crop extraction
  -> crop quality gate
  -> simple tracking / aggregation
  -> select best crops per track
  -> brand classifier on selected crops
  -> track-level brand aggregation
  -> video visibility metrics
  -> annotated media
  -> tables, crops, charts, report
```

For an image, the pipeline treats the image as a single-frame route.

For video, the MVP should process sampled frames first. Full frame-by-frame processing can be added later if needed.

## 1. Input Reader

Responsibilities:

- accept one input path: video or image;
- identify input type;
- for image: create one frame record;
- for video: sample frames by `frame_stride`;
- keep frame metadata: `frame_index`, `timestamp_sec`, `width`, `height`;
- compute `delta_t_sec` for sampled frames.

Initial MVP setting:

```text
frame_stride: 5
delta_t_sec: frame_stride / video_fps
```

Example:

```text
video_fps = 25
frame_stride = 5
delta_t_sec = 0.2 sec
```

Visibility metrics must use time weighting, otherwise results will depend too strongly on `frame_stride`.

## 2. Detection Gate

Run YOLO detector on each sampled frame and return detections before filtering.

Detection fields:

```text
frame_index
timestamp_sec
bbox_xyxy
det_class
det_conf
```

Detection gate decides whether the detection is worth saving at all.

Draft thresholds:

```text
detector_conf_min: 0.25-0.35
min_detection_width: 32 px
min_detection_height: 32 px
min_detection_area_ratio: 0.0005-0.001
```

These values are placeholders and must be tuned on real test video.

## 3. Crop Extraction

Save crop for every accepted detection.

Responsibilities:

- optionally expand bbox by a small margin before cropping;
- clip bbox to frame boundaries;
- save crop image;
- link crop path to detection row.

Initial setting:

```text
crop_margin_ratio: 0.05-0.10
```

Crop naming:

```text
frame_{frame_index:06d}_det_{det_index:03d}.jpg
```

Important: save crop even when classification will be skipped. Those crops are needed for debugging and manual review.

## 4. Classification Input Gate

Not every detection crop should be passed to the classifier.

This gate is not a statement about real-world human readability. It is only a technical estimate of whether this crop from this video is suitable as classifier input.

Draft thresholds:

```text
min_classify_width: 120 px
min_classify_height: 60 px
min_classify_area_ratio: 0.002-0.005
```

If crop is below threshold:

```text
crop_quality_status = rejected
crop_quality_reason = too_small_for_classification
classification_input_status = rejected
classification_attempted = false
brand_status = not_classified
brand = null
```

## 5. Crop Quality Gate

The crop quality gate returns:

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

Example logic:

```text
large enough, sharp enough, normal brightness:
  crop_quality_status = passed
  crop_quality_score = 0.85-1.0

imperfect crop, but classifier may still provide useful signal:
  crop_quality_status = borderline
  crop_quality_score = 0.45-0.75

too small or too blurred:
  crop_quality_status = rejected
  crop_quality_score = 0.0-0.45
```

If `crop_quality_status = rejected`, do not run classifier.

If `crop_quality_status = borderline`, classifier may run, but the final result should usually become `manual_review` unless classifier confidence is very high.

Use `not_classified` with reasons such as `small_crop_in_video`, `motion_blur_in_video`, or `low_video_quality`. Do not use final wording that implies the real-world ad is unreadable.

## 6. Tracking / Aggregation

Tracking is required because one ad object can appear on many sampled frames.

MVP tracking can use simple IoU association between neighboring sampled frames:

```text
if detection on frame N and detection on frame N + stride have IoU >= 0.3-0.5,
assign them to the same track_id
```

Track fields:

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

Later this can be upgraded to SORT/ByteTrack-style tracking, but simple IoU tracking is enough for the first MVP.

## 7. Best Crops Per Track

Do not classify every crop equally.

For every track, choose top-N best crops:

```text
best_crop_score = crop_quality_score * area_ratio * det_conf
best_crops_per_track: 3 or 5
```

Only selected best crops should go to the brand classifier.

This reduces noisy classifications from distant, tiny, blurred, or transitional frames.

## 8. Brand Classification

Run classifier only on crops where:

```text
crop_quality_status in [passed, borderline]
classification_input_status in [accepted, borderline]
```

Return:

```text
brand_pred
brand_conf
top1_brand
top1_score
top2_brand
top2_score
top3_brand
top3_score
```

Known classes:

```text
mts
plus7
miranda
other
```

The `other` class exists, but its acceptance threshold should still be configurable and may need to be stricter if the negative dataset is not diverse enough.

## 9. Track-Level Brand Aggregation

Final brand must be computed per track, not per single detection.

Example:

```text
crop_1: mts 0.82
crop_2: mts 0.76
crop_3: miranda 0.51
```

Result:

```text
final_brand = mts
final_brand_conf = mean/max confidence for mts
final_status = detected_brand or manual_review
```

Conflict case:

```text
crop_1: mts 0.72
crop_2: miranda 0.70
crop_3: plus7 0.66
```

Result:

```text
final_status = manual_review
final_brand = null or best candidate marked as conflict
status_reason = brand_conflict_across_track
```

Draft decision thresholds:

```text
brand_conf_accept: 0.80
other_conf_accept: 0.85
manual_review_min: 0.50
```

## 10. Status Model

Keep statuses separated by layer:

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

Reasons:

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

status_reason:
  ok
  brand_conf_low
  brand_conflict_across_track
  not_classified_crop_quality
  not_classified_no_valid_crop
```

Safe report wording:

```text
brand was not reliably determined from the available video material
```

Avoid wording that says the ad cannot be read in reality.

## 11. Video Visibility Metrics

We need route/video visibility, not just brand detection.

For every detection:

```text
area_ratio = bbox_area / frame_area
center_x_norm = bbox_center_x / frame_width
center_y_norm = bbox_center_y / frame_height
position_label = left/top, center-middle, right-bottom, etc.
```

Compute `position_weight`:

```text
center_distance = distance from frame center, normalized 0..1
position_weight = 1.0 - center_distance
position_weight clipped to 0.2..1.0
```

Frame-level geometry visibility:

```text
area_score = normalized area_ratio
geometry_visibility_score = area_score * position_weight
```

For MVP:

```text
video_visibility_score = geometry_visibility_score
```

Later we may add:

```text
video_visibility_score = geometry_visibility_score * detection_reliability_weight
```

Important: `crop_quality_score` must not automatically reduce visibility. A poor crop may hurt classifier reliability, but the ad surface may still be visible in the video.

Time-weighted visibility:

```text
video_visibility_weighted_seconds = video_visibility_score * delta_t_sec
```

Per-track metrics:

```text
track_video_visibility_score = sum or mean video_visibility_score over track detections
track_video_visibility_weighted_seconds = sum video_visibility_weighted_seconds
track_visible_duration_sec = last_timestamp_sec - first_timestamp_sec + delta_t_sec
track_max_area_ratio = max(area_ratio)
track_mean_area_ratio = mean(area_ratio)
```

Use time-weighted visibility so results are less dependent on `frame_stride`.

## 12. Scores

Keep multiple scores:

```text
det_score              = YOLO confidence
crop_quality_score     = crop suitability for classifier
brand_score            = classifier confidence
video_visibility_score = object visibility in this video
overall_score          = technical confidence score for result/card
```

Per-detection `overall_score`:

```text
overall_score =
  0.30 * det_conf +
  0.30 * crop_quality_score +
  0.25 * brand_conf +
  0.15 * video_visibility_score_norm
```

If classifier did not run:

```text
brand_conf = 0
overall_score =
  0.40 * det_conf +
  0.40 * crop_quality_score +
  0.20 * video_visibility_score_norm
```

Per-track `track_final_score`:

```text
track_final_score =
  0.30 * mean_det_conf +
  0.25 * best_crop_quality_score +
  0.25 * final_brand_conf +
  0.20 * track_video_visibility_score_norm
```

All weights should be configurable.

`overall_score` is not a replacement for `video_visibility_score`.

## Outputs

Each pipeline run should write to:

```text
outputs/pipeline/{run_id}/
```

Suggested structure:

```text
outputs/pipeline/{run_id}/
  input_meta.json
  detections.csv
  tracks.csv
  brand_summary_by_detections.csv
  brand_summary_by_tracks.csv
  frame_summary.csv

  crops/
    detected_brand/
      mts/
      plus7/
      miranda/
    other/
    unknown/
    manual_review/
    not_classified/

  frames/
    annotated/

  video/
    annotated_video.mp4

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

  report.html
```

For image input, `video/annotated_video.mp4` is not needed. The output should include an annotated image under `frames/annotated/`.

## detections.csv

One row per detection/crop.

Columns:

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

## tracks.csv

One row per unique ad object inside the video/route.

Columns:

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

Use `tracks.csv` for business counting.

Use `detections.csv` for frame-level debugging.

## Summaries

### brand_summary_by_detections.csv

Debug-oriented aggregation by raw detections.

### brand_summary_by_tracks.csv

Business-oriented aggregation by unique route objects.

Columns:

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

### frame_summary.csv

Frame-level view:

```text
frame_index
timestamp_sec
detections_total
detected_brand_count
other_count
unknown_count
manual_review_count
not_classified_count
sum_video_visibility_score
```

## Visualization Rules

Annotated media should use different colors by status:

```text
detected_brand: green
other: gray
unknown: yellow
manual_review: orange
not_classified: red or not drawn by default
```

Confirmed brand card:

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

Not classified card:

```text
Status: not_classified
Reason: small_crop_in_video
Det: 0.71
CropQ: 0.22
Area: 0.1%
Track: 8
```

For `manual_review`, `unknown`, and `not_classified`, do not draw the card as if the brand is confirmed.

## HTML Report

Report sections:

1. Detection summary:
   how many ad surfaces were detected frame-by-frame.
2. Track/object summary:
   how many unique ad objects were found on the route.
3. Brand summary:
   how many objects of each brand were found.
4. Visibility summary:
   `track_count`, `sum_video_visibility_score`, `mean_video_visibility_score`, `video_visibility_weighted_seconds`, `max_area_ratio`, `visible_duration_sec`.
5. Crop quality summary:
   how many objects were not classified because of `too_small_for_classification`, `small_crop_in_video`, `motion_blur_in_video`, `low_video_quality`, `low_confidence`.
6. Manual review gallery:
   crops that should be checked manually.
7. Best detections gallery:
   best crops by `track_final_score`.

Manual review priority:

```text
high video_visibility_score + low brand_conf
high video_visibility_score + brand_conflict_across_track
high video_visibility_score + not_classified
```

## MVP Config

Draft config:

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

All values must be configurable.

## MVP Implementation Order

1. Image pipeline:
   `image -> detector -> crops -> detections.csv -> annotated image`.
2. Video sampling:
   `video -> sampled frames -> detector -> detections.csv -> crops`.
3. Crop quality gate:
   `crop_quality_status`, `crop_quality_reason`, `crop_quality_score`.
4. Classification:
   run classifier only for `passed` / `borderline` crops.
5. Scoring:
   `det_score`, `crop_quality_score`, `brand_score`, `video_visibility_score`, `overall_score`.
6. Simple tracking:
   assign `track_id` through IoU association on neighboring sampled frames.
7. Track aggregation:
   best crops, final brand, final status, track final score.
8. Reports:
   `detections.csv`, `tracks.csv`, summaries.
9. Visualization:
   annotated frames/video with cards.
10. Charts + HTML report.

## Key Business Questions

`detections.csv` answers:

```text
What did the model see on each sampled frame?
```

`tracks.csv` answers:

```text
Which unique advertising objects were present on the route?
```

`brand_summary_by_tracks.csv` answers:

```text
How many unique objects of each brand were found?
```

`video_visibility_by_brand` answers:

```text
How visible was each brand in this video/route?
```
