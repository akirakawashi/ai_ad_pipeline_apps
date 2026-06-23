"""Detection crop helpers."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import shutil

import cv2
import numpy as np

from .config import PipelineConfig
from .domain import FinalStatus
from .schemas import DetectionRecord, FrameRecord, TrackRecord

CropBox = tuple[int, int, int, int]


def save_detection_crops(
    detections: list[DetectionRecord],
    frames_by_index: dict[int, FrameRecord],
    crops_dir: Path,
    config: PipelineConfig,
) -> None:
    crops_dir.mkdir(parents=True, exist_ok=True)

    for detection in detections:
        frame = frames_by_index[detection.frame_index]
        crop, crop_box = crop_detection(
            frame, detection, config.classification.crop_margin_ratio
        )
        if crop.size == 0:
            detection.crop_path = ""
            detection.crop_width = 0
            detection.crop_height = 0
            continue

        crop_name = (
            f"frame_{detection.frame_index:06d}_det_{detection.det_index:03d}.jpg"
        )
        crop_path = crops_dir / crop_name
        if not cv2.imwrite(str(crop_path), crop):
            raise RuntimeError(f"Could not write crop: {crop_path}")
        detection.crop_path = str(crop_path)
        detection.crop_width = int(crop.shape[1])
        detection.crop_height = int(crop.shape[0])

        x1, y1, x2, y2 = crop_box
        if x1 <= 0 or y1 <= 0 or x2 >= frame.width - 1 or y2 >= frame.height - 1:
            if detection.crop_quality_reason == "not_evaluated":
                detection.crop_quality_reason = "clipped_by_frame_border"


def crop_detection(
    frame: FrameRecord,
    detection: DetectionRecord,
    margin_ratio: float,
) -> tuple[np.ndarray, CropBox]:
    x1, y1, x2, y2 = detection.bbox_xyxy
    width = x2 - x1
    height = y2 - y1
    margin_x = width * margin_ratio
    margin_y = height * margin_ratio

    crop_x1 = max(0, int(round(x1 - margin_x)))
    crop_y1 = max(0, int(round(y1 - margin_y)))
    crop_x2 = min(frame.width, int(round(x2 + margin_x)))
    crop_y2 = min(frame.height, int(round(y2 + margin_y)))

    crop = frame.image[crop_y1:crop_y2, crop_x1:crop_x2].copy()
    return crop, (crop_x1, crop_y1, crop_x2, crop_y2)


def copy_crops_by_status(
    detections: list[DetectionRecord],
    tracks_by_id: Mapping[int, TrackRecord],
    crops_root: Path,
) -> None:
    for detection in detections:
        if not detection.crop_path:
            continue
        track = tracks_by_id.get(detection.track_id or -1)
        if track is None:
            status_parts = ["unknown"]
        elif track.final_status == FinalStatus.DETECTED_BRAND and track.final_brand:
            status_parts = [FinalStatus.DETECTED_BRAND, track.final_brand]
        else:
            status_parts = [track.final_status]

        destination_dir = crops_root.joinpath(*status_parts)
        destination_dir.mkdir(parents=True, exist_ok=True)
        source = Path(detection.crop_path)
        if source.exists():
            shutil.copy2(source, destination_dir / source.name)
