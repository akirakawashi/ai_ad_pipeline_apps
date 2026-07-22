"""Фактор контраста к фону C (0…1) — новый CV-шаг (v1: по яркости).

Считаем яркостной контраст Михельсона между регионом щита (bbox) и кольцом-фоном
вокруг него: contrast = |L_щит − L_кольцо| / (L_щит + L_кольцо) ∈ [0, 1].
Затем прогоняем через таблицу порогов (ScoringConfig.contrast) с интерполяцией.
Яркость = среднее по каналам (устойчиво к порядку RGB/BGR).
"""

from __future__ import annotations

import numpy as np

from ..config import PipelineConfig
from ..schemas import DetectionRecord, FrameRecord
from .interpolation import piecewise_linear


def contrast_coefficient(
    detection: DetectionRecord, frame: FrameRecord, config: PipelineConfig
) -> float:
    cfg = config.scoring.contrast
    floor = cfg.points[0][1]

    image = frame.image
    if image is None or getattr(image, "size", 0) == 0:
        return floor

    height, width = image.shape[:2]
    x1 = max(0, int(detection.bbox_x1))
    y1 = max(0, int(detection.bbox_y1))
    x2 = min(width, int(round(detection.bbox_x2)))
    y2 = min(height, int(round(detection.bbox_y2)))
    if x2 <= x1 or y2 <= y1:
        return floor

    luminance = image.astype(np.float32)
    if luminance.ndim == 3:
        luminance = luminance.mean(axis=2)

    margin_x = int(round((x2 - x1) * cfg.ring_margin_ratio))
    margin_y = int(round((y2 - y1) * cfg.ring_margin_ratio))
    ox1 = max(0, x1 - margin_x)
    oy1 = max(0, y1 - margin_y)
    ox2 = min(width, x2 + margin_x)
    oy2 = min(height, y2 + margin_y)

    inner = luminance[y1:y2, x1:x2]
    outer = luminance[oy1:oy2, ox1:ox2]
    if inner.size == 0 or outer.size <= inner.size:
        return floor

    l_object = float(inner.mean())
    l_ring = float((outer.sum() - inner.sum()) / (outer.size - inner.size))

    denominator = l_object + l_ring
    contrast = abs(l_object - l_ring) / denominator if denominator > 1e-6 else 0.0

    return piecewise_linear(contrast, cfg.points)
