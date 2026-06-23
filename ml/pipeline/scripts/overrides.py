"""Manual brand override helpers."""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path

from .domain import (
    BrandStatus,
    FinalStatus,
    IGNORE_BRAND,
    VALID_OVERRIDE_BRANDS,
    normalize_brand_name,
)
from .schemas import DetectionRecord, TrackRecord

logger = logging.getLogger(__name__)
VALID_BRANDS = VALID_OVERRIDE_BRANDS


@dataclass(frozen=True)
class BrandOverride:
    track_id: int | None
    crop_name: str
    brand: str
    reason: str


def apply_brand_overrides(
    tracks: list[TrackRecord],
    detections: list[DetectionRecord],
    overrides_path: Path | None,
) -> int:
    if overrides_path is None:
        return 0
    if not overrides_path.exists():
        raise FileNotFoundError(overrides_path)

    overrides = read_brand_overrides(overrides_path)
    tracks_by_id = {track.track_id: track for track in tracks}
    tracks_by_object: dict[int, list[TrackRecord]] = {}
    detections_by_track: dict[int, list[DetectionRecord]] = {}
    detections_by_object: dict[int, list[DetectionRecord]] = {}
    crop_name_to_track_id: dict[str, int] = {}
    for track_record in tracks:
        tracks_by_object.setdefault(track_record.object_id, []).append(track_record)
    for detection in detections:
        if detection.track_id is None:
            continue
        detections_by_track.setdefault(detection.track_id, []).append(detection)
        if detection.object_id is not None:
            detections_by_object.setdefault(detection.object_id, []).append(detection)
        if detection.crop_path:
            crop_name_to_track_id[Path(detection.crop_path).name] = detection.track_id

    applied = 0
    for override in overrides:
        track_id = override.track_id
        if track_id is None and override.crop_name:
            track_id = crop_name_to_track_id.get(override.crop_name)
        if track_id is None:
            logger.warning(
                "brand override skipped: track not found for crop=%s",
                override.crop_name,
            )
            continue

        matched_track = tracks_by_id.get(track_id)
        if matched_track is None:
            logger.warning(
                "brand override skipped: track_id=%s not found",
                track_id,
            )
            continue

        target_tracks = tracks_by_object.get(matched_track.object_id, [matched_track])
        target_detections = detections_by_object.get(
            matched_track.object_id,
            detections_by_track.get(track_id, []),
        )
        for target_track in target_tracks:
            apply_track_override(target_track, override.brand, override.reason)
        for detection in target_detections:
            apply_detection_override(detection, override.brand, override.reason)
        applied += 1

    return applied


def read_brand_overrides(path: Path) -> list[BrandOverride]:
    overrides: list[BrandOverride] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            track_id = parse_track_id(row.get("track_id", ""))
            crop_name = row.get("crop_name", "").strip()
            brand = normalize_brand(row.get("brand", ""))
            reason = row.get("reason", "").strip() or "manual_override"
            if track_id is None and not crop_name:
                raise ValueError(
                    f"Override row must contain track_id or crop_name: {row}"
                )
            overrides.append(
                BrandOverride(
                    track_id=track_id,
                    crop_name=crop_name,
                    brand=brand,
                    reason=reason,
                )
            )
    return overrides


def parse_track_id(value: str) -> int | None:
    normalized = value.strip()
    if not normalized:
        return None
    return int(normalized)


def normalize_brand(value: str) -> str:
    brand = normalize_brand_name(value)
    if brand not in VALID_OVERRIDE_BRANDS:
        raise ValueError(f"Unsupported override brand: {value}")
    return brand


def apply_track_override(track: TrackRecord, brand: str, reason: str) -> None:
    if brand == IGNORE_BRAND:
        apply_track_ignore_override(track, reason)
        return

    track.final_brand = brand
    track.final_brand_conf = 1.0
    track.final_status = (
        FinalStatus.OTHER if brand == "other" else FinalStatus.DETECTED_BRAND
    )
    track.business_brand = brand
    track.business_visible = True
    track.final_status_reason = f"manual_override:{reason}"
    track.manual_review_required = False
    track.track_final_score = (
        0.30 * track.mean_det_conf
        + 0.25 * track.best_crop_quality_score
        + 0.25 * track.final_brand_conf
        + 0.20 * track.mean_video_visibility_score
    )


def apply_detection_override(
    detection: DetectionRecord, brand: str, reason: str
) -> None:
    if brand == IGNORE_BRAND:
        apply_detection_ignore_override(detection, reason)
        return

    detection.brand_pred = brand
    detection.brand_conf = 1.0
    detection.top1_brand = brand
    detection.top1_score = 1.0
    detection.brand_status = (
        BrandStatus.OTHER if brand == "other" else BrandStatus.DETECTED_BRAND
    )
    detection.final_status = (
        FinalStatus.OTHER if brand == "other" else FinalStatus.DETECTED_BRAND
    )
    detection.business_brand = brand
    detection.business_visible = True
    detection.status_reason = f"manual_override:{reason}"


def apply_track_ignore_override(track: TrackRecord, reason: str) -> None:
    track.final_brand = ""
    track.final_brand_conf = 0.0
    track.final_status = FinalStatus.IGNORED
    track.business_brand = "other"
    track.business_visible = False
    track.final_status_reason = f"manual_ignore:{reason}"
    track.manual_review_required = False


def apply_detection_ignore_override(detection: DetectionRecord, reason: str) -> None:
    detection.brand_pred = ""
    detection.brand_conf = 0.0
    detection.top1_brand = ""
    detection.top1_score = 0.0
    detection.brand_status = BrandStatus.IGNORED
    detection.final_status = FinalStatus.IGNORED
    detection.business_brand = "other"
    detection.business_visible = False
    detection.status_reason = f"manual_ignore:{reason}"
