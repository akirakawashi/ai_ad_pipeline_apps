"""Video visibility metric helpers."""

from __future__ import annotations

import math

from .config import PipelineConfig
from .schemas import DetectionRecord, FrameRecord


def fill_geometry_fields(
    detection: DetectionRecord,
    frame: FrameRecord,
    config: PipelineConfig,
) -> None:
    detection.center_x = (detection.bbox_x1 + detection.bbox_x2) / 2.0
    detection.center_y = (detection.bbox_y1 + detection.bbox_y2) / 2.0
    detection.center_x_norm = detection.center_x / max(1, frame.width)
    detection.center_y_norm = detection.center_y / max(1, frame.height)
    detection.position_label = position_label(
        detection.center_x_norm, detection.center_y_norm
    )
    detection.position_weight = position_weight(
        detection.center_x_norm,
        detection.center_y_norm,
        config.visibility.min_position_weight,
    )
    area_score = min(
        1.0,
        detection.area_ratio / max(1e-9, config.visibility.area_norm),
    )
    detection.video_visibility_score = area_score * detection.position_weight
    detection.video_visibility_weighted_seconds = (
        detection.video_visibility_score * frame.delta_t_sec
    )


def position_weight(
    center_x_norm: float, center_y_norm: float, minimum: float
) -> float:
    dx = center_x_norm - 0.5
    dy = center_y_norm - 0.5
    max_distance = math.sqrt(0.5**2 + 0.5**2)
    distance = math.sqrt(dx * dx + dy * dy) / max_distance
    return max(minimum, min(1.0, 1.0 - distance))


def position_label(center_x_norm: float, center_y_norm: float) -> str:
    horizontal = (
        "left"
        if center_x_norm < 1 / 3
        else "right"
        if center_x_norm > 2 / 3
        else "center"
    )
    vertical = (
        "top"
        if center_y_norm < 1 / 3
        else "bottom"
        if center_y_norm > 2 / 3
        else "middle"
    )
    return f"{horizontal}-{vertical}"
