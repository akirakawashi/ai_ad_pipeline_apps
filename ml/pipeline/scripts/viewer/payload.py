"""Build serializable overlay payloads for the HTML viewer."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

from ..config import PipelineConfig
from ..domain import TARGET_BRANDS
from ..schemas import DetectionRecord, InputMetadata, TrackRecord
from ..visualization import build_render_detections_by_frame
from .constants import BRAND_STYLES


def build_overlay_payload(
    output_dir: Path,
    metadata: InputMetadata,
    detections: list[DetectionRecord],
    tracks: list[TrackRecord],
    config: PipelineConfig,
) -> dict[str, Any]:
    tracks_by_id = {track.track_id: track for track in tracks}
    render_detections_by_frame = build_render_detections_by_frame(
        detections, metadata, config
    )
    frames: list[dict[str, Any]] = []

    for frame_index, frame_detections in sorted(render_detections_by_frame.items()):
        objects = [
            detection_to_overlay_object(
                detection, tracks_by_id.get(detection.track_id or -1)
            )
            for detection in frame_detections
        ]
        if not objects:
            continue
        frames.append(
            {
                "frame_index": frame_index,
                "timestamp_sec": frame_timestamp(frame_index, metadata),
                "objects": objects,
            }
        )

    return {
        "version": 1,
        "video": {
            "source": relative_video_source(output_dir, metadata.source_path),
            "width": metadata.width,
            "height": metadata.height,
            "fps": metadata.fps,
            "frame_count": metadata.frame_count,
            "frame_stride": metadata.frame_stride,
        },
        "display": {
            "max_cards_per_frame": 5,
            "fields": [
                "class",
                "det_conf",
                "brand_conf",
                "area_ratio",
                "visibility_score",
                "overall_score",
            ],
        },
        "frames": frames,
    }


def detection_to_overlay_object(
    detection: DetectionRecord,
    track: TrackRecord | None,
) -> dict[str, Any]:
    brand = (track.business_brand if track else detection.business_brand) or "other"
    style = BRAND_STYLES.get(brand, BRAND_STYLES["other"])
    brand_conf = track.final_brand_conf if track else detection.brand_conf
    overall_score = track.track_final_score if track else detection.overall_score

    return {
        "object_id": detection.object_id,
        "track_id": detection.track_id,
        "brand": brand,
        "label": style["label"],
        "color": style["color"],
        "bbox": [
            round(detection.bbox_x1, 2),
            round(detection.bbox_y1, 2),
            round(detection.bbox_x2, 2),
            round(detection.bbox_y2, 2),
        ],
        "det_conf": round(detection.det_conf, 4),
        "brand_conf": round(brand_conf, 4),
        "area_ratio": round(detection.area_ratio, 6),
        "visibility_score": round(detection.video_visibility_score, 4),
        "overall_score": round(overall_score, 4),
        "card_priority": card_priority(brand, detection.area_ratio, overall_score),
    }


def card_priority(brand: str, area_ratio: float, overall_score: float) -> float:
    brand_weight = 1000.0 if brand in TARGET_BRANDS else 0.0
    return brand_weight + 100.0 * area_ratio + overall_score


def frame_timestamp(frame_index: int, metadata: InputMetadata) -> float:
    if metadata.fps > 0:
        return frame_index / metadata.fps
    return frame_index * metadata.delta_t_sec


def relative_video_source(output_dir: Path, source_path: Path) -> str:
    relative = Path(os.path.relpath(source_path, output_dir)).as_posix()
    return quote(relative, safe="/.:_-")
