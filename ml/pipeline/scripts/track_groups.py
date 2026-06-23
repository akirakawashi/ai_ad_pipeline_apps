"""Post-processing for non-real-time object-level track groups."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import hypot

from .config import PipelineConfig
from .domain import TARGET_BRANDS
from .schemas import DetectionRecord, TrackRecord
from .tracking import bbox_iou


@dataclass(frozen=True)
class TrackFragment:
    track: TrackRecord
    detections: list[DetectionRecord]
    first_detection: DetectionRecord
    last_detection: DetectionRecord


def assign_object_groups(
    tracks: list[TrackRecord],
    detections: list[DetectionRecord],
    config: PipelineConfig,
) -> int:
    fragments = build_track_fragments(tracks, detections)
    assigned_fragments: list[TrackFragment] = []
    next_object_id = 1

    for fragment in fragments:
        object_id = find_best_object_id(fragment, assigned_fragments, config)
        if object_id is None:
            object_id = next_object_id
            next_object_id += 1

        fragment.track.object_id = object_id
        for detection in fragment.detections:
            detection.object_id = object_id
        assigned_fragments.append(fragment)

    return next_object_id - 1


def stabilize_object_brands(
    tracks: list[TrackRecord],
    detections: list[DetectionRecord],
    config: PipelineConfig,
) -> int:
    tracks_by_object: dict[int, list[TrackRecord]] = defaultdict(list)
    detections_by_object: dict[int, list[DetectionRecord]] = defaultdict(list)

    for track in tracks:
        tracks_by_object[track.object_id].append(track)
    for detection in detections:
        if detection.object_id is not None:
            detections_by_object[detection.object_id].append(detection)

    changed = 0
    for object_id, object_tracks in tracks_by_object.items():
        brand = choose_object_business_brand(object_tracks)
        object_detections = detections_by_object.get(object_id, [])
        visible = is_business_visible(object_tracks, object_detections, config)
        for track in object_tracks:
            if track.business_brand != brand:
                changed += 1
            track.business_brand = brand
            track.business_visible = visible
        for detection in object_detections:
            detection.business_brand = brand
            detection.business_visible = visible

    return changed


def build_track_fragments(
    tracks: list[TrackRecord],
    detections: list[DetectionRecord],
) -> list[TrackFragment]:
    detections_by_track: dict[int, list[DetectionRecord]] = defaultdict(list)
    for detection in detections:
        if detection.track_id is not None:
            detections_by_track[detection.track_id].append(detection)

    fragments: list[TrackFragment] = []
    for track in tracks:
        track_detections = sorted(
            detections_by_track.get(track.track_id, []),
            key=lambda detection: detection.frame_index,
        )
        if not track_detections:
            continue
        fragments.append(
            TrackFragment(
                track=track,
                detections=track_detections,
                first_detection=track_detections[0],
                last_detection=track_detections[-1],
            )
        )

    return sorted(
        fragments,
        key=lambda fragment: (
            fragment.track.first_frame_index,
            fragment.track.last_frame_index,
            fragment.track.track_id,
        ),
    )


def find_best_object_id(
    fragment: TrackFragment,
    assigned_fragments: list[TrackFragment],
    config: PipelineConfig,
) -> int | None:
    best_object_id: int | None = None
    best_score = 0.0
    skipped_object_ids: set[int] = set()

    for candidate in assigned_fragments:
        object_id = candidate.track.object_id
        if object_id in skipped_object_ids:
            continue
        if object_has_temporal_overlap(fragment, assigned_fragments, object_id):
            skipped_object_ids.add(object_id)
            continue

        score = track_link_score(candidate, fragment, config)
        if score > best_score:
            best_score = score
            best_object_id = object_id

    return best_object_id


def object_has_temporal_overlap(
    fragment: TrackFragment,
    assigned_fragments: list[TrackFragment],
    object_id: int,
) -> bool:
    return any(
        candidate.track.object_id == object_id
        and fragments_overlap_in_time(candidate, fragment)
        for candidate in assigned_fragments
    )


def fragments_overlap_in_time(first: TrackFragment, second: TrackFragment) -> bool:
    return (
        first.track.first_frame_index <= second.track.last_frame_index
        and second.track.first_frame_index <= first.track.last_frame_index
    )


def track_link_score(
    previous: TrackFragment,
    current: TrackFragment,
    config: PipelineConfig,
) -> float:
    frame_gap = current.track.first_frame_index - previous.track.last_frame_index
    if frame_gap < 0 or frame_gap > config.tracking.object_merge_max_gap_frames:
        return 0.0

    previous_detection = previous.last_detection
    current_detection = current.first_detection
    iou = bbox_iou(previous_detection.bbox_xyxy, current_detection.bbox_xyxy)
    center_distance = hypot(
        previous_detection.center_x_norm - current_detection.center_x_norm,
        previous_detection.center_y_norm - current_detection.center_y_norm,
    )

    iou_ok = iou >= config.tracking.object_merge_min_iou
    center_ok = center_distance <= config.tracking.object_merge_max_center_distance
    if not iou_ok and not center_ok:
        return 0.0

    if (
        ratio(previous_detection.area_ratio, current_detection.area_ratio)
        > config.tracking.object_merge_max_area_ratio
    ):
        return 0.0
    if (
        ratio(previous_detection.bbox_aspect_ratio, current_detection.bbox_aspect_ratio)
        > config.tracking.object_merge_max_aspect_ratio
    ):
        return 0.0

    gap_score = 1.0 - (
        frame_gap / max(1.0, float(config.tracking.object_merge_max_gap_frames))
    )
    center_score = 1.0 - min(
        1.0,
        center_distance / max(1e-9, config.tracking.object_merge_max_center_distance),
    )
    return 2.0 * iou + center_score + 0.25 * gap_score


def ratio(first: float, second: float) -> float:
    if first <= 0 or second <= 0:
        return float("inf")
    return max(first, second) / min(first, second)


def choose_object_business_brand(tracks: list[TrackRecord]) -> str:
    manual_scores: dict[str, float] = defaultdict(float)
    model_scores: dict[str, float] = defaultdict(float)

    for track in tracks:
        score = max(
            track.video_visibility_weighted_seconds, track.visible_duration_sec, 1.0
        )
        score *= max(track.final_brand_conf, 0.01)
        if track.final_status_reason.startswith("manual_override:"):
            manual_scores[track.business_brand] += score
        elif track.business_brand in TARGET_BRANDS:
            model_scores[track.business_brand] += score

    if manual_scores:
        return max(manual_scores.items(), key=lambda item: item[1])[0]
    if model_scores:
        return max(model_scores.items(), key=lambda item: item[1])[0]
    return "other"


def is_business_visible(
    tracks: list[TrackRecord],
    detections: list[DetectionRecord],
    config: PipelineConfig,
) -> bool:
    if any(track.final_status_reason.startswith("manual_ignore:") for track in tracks):
        return False
    if any(
        track.final_status_reason.startswith("manual_override:") for track in tracks
    ):
        return True
    if len(detections) < config.business.min_object_detections:
        return False
    if not detections:
        return False
    first_timestamp = min(detection.timestamp_sec for detection in detections)
    last_timestamp = max(detection.timestamp_sec for detection in detections)
    max_delta = max(detection.sample_delta_t_sec for detection in detections)
    visible_duration = max(0.0, last_timestamp - first_timestamp + max_delta)
    return visible_duration >= config.business.min_visible_duration_sec
