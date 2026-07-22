"""Track-level aggregation helpers."""

from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean

from .config import PipelineConfig
from .domain import FinalStatus, TARGET_BRANDS
from .schemas import DetectionRecord, TrackRecord
from .scoring import (
    attention_seconds,
    confidence_coefficient,
    significance_coefficient,
    visibility_value,
)


def build_tracks(
    detections: list[DetectionRecord],
    config: PipelineConfig,
) -> list[TrackRecord]:
    """Build track summaries without mutating detection-level final results."""
    grouped: dict[int, list[DetectionRecord]] = defaultdict(list)
    for detection in detections:
        if detection.track_id is None:
            continue
        grouped[detection.track_id].append(detection)

    tracks: list[TrackRecord] = []
    for track_id, track_detections in sorted(grouped.items()):
        ordered = sorted(track_detections, key=lambda item: item.timestamp_sec)
        track = _aggregate_one(track_id, ordered, config)
        tracks.append(track)
    return tracks


def apply_track_results(
    tracks: list[TrackRecord],
    detections: list[DetectionRecord],
) -> None:
    """Propagate final track-level decisions back to their detections."""
    tracks_by_id = {track.track_id: track for track in tracks}
    for detection in detections:
        if detection.track_id is None:
            continue
        track = tracks_by_id.get(detection.track_id)
        if track is None:
            continue
        detection.final_status = track.final_status
        detection.business_brand = track.business_brand
        detection.status_reason = track.final_status_reason


def _aggregate_one(
    track_id: int,
    detections: list[DetectionRecord],
    config: PipelineConfig,
) -> TrackRecord:
    best_detection = max(detections, key=_best_detection_score)
    classified = [
        detection for detection in detections if detection.classification_attempted
    ]
    final_brand, final_conf, final_status, final_reason = _aggregate_brand(
        classified, config
    )
    track_confirmed = _is_track_confirmed(detections, config)
    if not track_confirmed:
        final_brand = ""
        final_conf = 0.0
        final_status = FinalStatus.NOT_CLASSIFIED
        final_reason = "short_track_in_video"
    if final_status == FinalStatus.NOT_CLASSIFIED:
        final_reason = _dominant_not_classified_reason(detections)
        if not track_confirmed:
            final_reason = "short_track_in_video"

    visible_duration_sec = (
        detections[-1].timestamp_sec
        - detections[0].timestamp_sec
        + max(detection.sample_delta_t_sec for detection in detections)
    )
    if visible_duration_sec < 0:
        visible_duration_sec = 0.0

    object_attention_seconds = attention_seconds(detections)
    object_confidence_coef = confidence_coefficient(detections, final_conf, config)
    object_significance_coef = significance_coefficient(detections, config)
    object_visibility_value = visibility_value(
        object_attention_seconds, object_confidence_coef, object_significance_coef
    )

    return TrackRecord(
        run_id=detections[0].run_id,
        source_path=detections[0].source_path,
        track_id=track_id,
        object_id=_track_object_id(detections, track_id),
        first_frame_index=detections[0].frame_index,
        last_frame_index=detections[-1].frame_index,
        first_timestamp_sec=detections[0].timestamp_sec,
        last_timestamp_sec=detections[-1].timestamp_sec,
        visible_duration_sec=visible_duration_sec,
        detections_count=len(detections),
        best_crop_path=best_detection.crop_path,
        best_timestamp_sec=best_detection.timestamp_sec,
        attention_seconds=object_attention_seconds,
        confidence_coef=object_confidence_coef,
        significance_coef=object_significance_coef,
        visibility_value=object_visibility_value,
        final_brand=final_brand,
        final_brand_conf=final_conf,
        final_status=final_status,
        business_brand=_business_brand(final_brand, final_status),
        business_visible=False,
        final_status_reason=final_reason,
        track_confirmed=track_confirmed,
        manual_review_required=final_status == FinalStatus.MANUAL_REVIEW,
    )


def _aggregate_brand(
    detections: list[DetectionRecord],
    config: PipelineConfig,
) -> tuple[str, float, FinalStatus, str]:
    if not detections:
        return (
            "",
            0.0,
            FinalStatus.NOT_CLASSIFIED,
            "not_classified_no_valid_crop",
        )

    scores: dict[str, list[float]] = defaultdict(list)
    for detection in detections:
        if detection.brand_pred:
            scores[detection.brand_pred].append(detection.brand_conf)

    if not scores:
        return "", 0.0, FinalStatus.UNKNOWN, "brand_conf_low"

    brand_scores = {brand: mean(values) for brand, values in scores.items()}
    ordered = sorted(brand_scores.items(), key=lambda item: item[1], reverse=True)
    top_brand, top_conf = ordered[0]
    second_conf = ordered[1][1] if len(ordered) > 1 else 0.0
    vote_counts = Counter(
        detection.brand_pred for detection in detections if detection.brand_pred
    )
    conflict = (
        len(vote_counts) > 1
        and top_conf >= config.classification.manual_review_min
        and top_conf - second_conf < config.classification.conflict_margin
    )
    if conflict:
        return (
            "",
            top_conf,
            FinalStatus.MANUAL_REVIEW,
            "brand_conflict_across_track",
        )

    if top_brand == "other":
        if top_conf >= config.classification.other_confidence_accept:
            return "other", top_conf, FinalStatus.OTHER, "ok"
        if top_conf >= config.classification.manual_review_min:
            return "other", top_conf, FinalStatus.MANUAL_REVIEW, "brand_conf_low"
        return "", top_conf, FinalStatus.UNKNOWN, "brand_conf_low"

    if top_brand in TARGET_BRANDS:
        if top_conf >= config.classification.brand_confidence_accept:
            return top_brand, top_conf, FinalStatus.DETECTED_BRAND, "ok"
        if top_conf >= config.classification.manual_review_min:
            return (
                top_brand,
                top_conf,
                FinalStatus.MANUAL_REVIEW,
                "brand_conf_low",
            )
        return "", top_conf, FinalStatus.UNKNOWN, "brand_conf_low"

    return "", top_conf, FinalStatus.UNKNOWN, "brand_conf_low"


def _business_brand(final_brand: str, final_status: FinalStatus) -> str:
    """Наружу отдаём только «наш бренд» либо «other».

    Всё, в чём модель не уверена (UNKNOWN, MANUAL_REVIEW, NOT_CLASSIFIED),
    схлопывается в other намеренно: пользователю нужен ответ «телеком или нет»,
    а не градации уверенности.
    """
    if final_status == FinalStatus.DETECTED_BRAND and final_brand in TARGET_BRANDS:
        return final_brand
    if final_status == FinalStatus.OTHER and final_brand == "other":
        return final_brand
    return "other"


def _track_object_id(detections: list[DetectionRecord], default: int) -> int:
    object_ids = [
        detection.object_id
        for detection in detections
        if detection.object_id is not None
    ]
    if not object_ids:
        return default
    return Counter(object_ids).most_common(1)[0][0]


def _dominant_not_classified_reason(detections: list[DetectionRecord]) -> str:
    reasons = [
        detection.crop_quality_reason
        for detection in detections
        if detection.crop_quality_reason
        and detection.crop_quality_reason not in {"ok", "not_evaluated"}
    ]
    if not reasons:
        return "not_classified_no_valid_crop"
    return Counter(reasons).most_common(1)[0][0]


def _is_track_confirmed(
    detections: list[DetectionRecord], config: PipelineConfig
) -> bool:
    if detections[0].input_type == "image":
        return True
    frame_span = detections[-1].frame_index - detections[0].frame_index
    return (
        len(detections) >= config.tracking.min_detections
        and frame_span >= config.tracking.min_frame_span
    )


def _best_detection_score(detection: DetectionRecord) -> float:
    return detection.crop_quality_score * detection.area_ratio * detection.det_conf
