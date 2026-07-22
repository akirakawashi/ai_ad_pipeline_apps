"""Build serializable overlay payloads for the HTML viewer."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote

from ..artifacts import (
    OverlayDisplayPayload,
    OverlayFramePayload,
    OverlayObjectPayload,
    OverlayPayload,
    OverlayVideoPayload,
)
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
) -> OverlayPayload:
    tracks_by_id = {track.track_id: track for track in tracks}
    render_detections_by_frame = build_render_detections_by_frame(
        detections, metadata, config
    )
    frames: list[OverlayFramePayload] = []

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
            OverlayFramePayload(
                frame_index=frame_index,
                timestamp_sec=frame_timestamp(frame_index, metadata),
                objects=objects,
            )
        )

    return OverlayPayload(
        version=1,
        video=OverlayVideoPayload(
            source=relative_video_source(output_dir, metadata.source_path),
            width=metadata.width,
            height=metadata.height,
            fps=metadata.fps,
            frame_count=metadata.frame_count,
            frame_stride=metadata.frame_stride,
        ),
        display=OverlayDisplayPayload(
            max_cards_per_frame=5,
            fields=[
                "class",
                "det_conf",
                "brand_conf",
                "area_ratio",
                "intensity",
                "visibility_value",
            ],
        ),
        frames=frames,
    )


def detection_to_overlay_object(
    detection: DetectionRecord,
    track: TrackRecord | None,
) -> OverlayObjectPayload:
    brand = (track.business_brand if track else detection.business_brand) or "other"
    style = BRAND_STYLES.get(brand, BRAND_STYLES["other"])
    brand_conf = track.final_brand_conf if track else detection.brand_conf
    object_value = track.visibility_value if track else detection.intensity

    return OverlayObjectPayload(
        object_id=detection.object_id,
        track_id=detection.track_id,
        brand=brand,
        label=style["label"],
        color=style["color"],
        bbox=(
            round(detection.bbox_x1, 2),
            round(detection.bbox_y1, 2),
            round(detection.bbox_x2, 2),
            round(detection.bbox_y2, 2),
        ),
        det_conf=round(detection.det_conf, 4),
        brand_conf=round(brand_conf, 4),
        area_ratio=round(detection.area_ratio, 6),
        intensity=round(detection.intensity, 4),
        visibility_value=round(object_value, 4),
        card_priority=card_priority(brand, detection.area_ratio, object_value),
    )


def card_priority(brand: str, area_ratio: float, value: float) -> float:
    brand_weight = 1000.0 if brand in TARGET_BRANDS else 0.0
    return brand_weight + 100.0 * area_ratio + value


def frame_timestamp(frame_index: int, metadata: InputMetadata) -> float:
    if metadata.fps > 0:
        return frame_index / metadata.fps
    return frame_index * metadata.delta_t_sec


def relative_video_source(output_dir: Path, source_path: Path) -> str:
    relative = Path(os.path.relpath(source_path, output_dir)).as_posix()
    return quote(relative, safe="/.:_-")
