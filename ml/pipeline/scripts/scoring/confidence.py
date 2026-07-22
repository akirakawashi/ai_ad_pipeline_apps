"""Коэффициент уверенности α — отдельная ось (атрибуция бренду).

v1: только величина уверенности бренда (final_brand_conf) через таблицу порогов
с интерполяцией. Стабильность бренда по треку — задел на будущее (пока не учитываем).
Пол 0.5: объект всё равно видели, в ноль уверенность не режет.
"""

from __future__ import annotations

from collections.abc import Iterable

from ..config import PipelineConfig
from ..schemas import DetectionRecord
from .interpolation import piecewise_linear


def confidence_coefficient(
    detections: Iterable[DetectionRecord],
    final_brand_conf: float,
    config: PipelineConfig,
) -> float:
    # detections — задел под стабильность бренда (v2); в v1 не используется.
    return piecewise_linear(final_brand_conf, config.scoring.confidence.points)
