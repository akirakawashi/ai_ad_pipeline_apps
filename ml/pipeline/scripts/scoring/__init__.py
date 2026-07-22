"""Слой расчёта метрики заметности (новая логика).

Извлечение признаков (area / position / contrast / …) отдельно от сборки
балла (combiner). Формулы:
    I = A · P · C            (на кадр)
    S = Σ (I · Δt)           (на объект — секунды внимания)
    V = S · α · β            (итоговый балл объекта)
"""

from __future__ import annotations

from ..config import PipelineConfig
from ..schemas import DetectionRecord, FrameRecord
from .area import area_coefficient
from .attention import attention_seconds
from .combiner import visibility_value
from .confidence import confidence_coefficient
from .contrast import contrast_coefficient
from .geometry import fill_geometry
from .intensity import intensity
from .position import position_coefficient
from .significance import significance_coefficient

__all__ = [
    "area_coefficient",
    "attention_seconds",
    "confidence_coefficient",
    "contrast_coefficient",
    "fill_detection_scoring",
    "fill_geometry",
    "intensity",
    "position_coefficient",
    "significance_coefficient",
    "visibility_value",
]


def fill_detection_scoring(
    detection: DetectionRecord, frame: FrameRecord, config: PipelineConfig
) -> None:
    """Геометрия + мгновенные коэффициенты и интенсивность на одну детекцию."""
    fill_geometry(detection, frame)
    detection.area_coef = area_coefficient(detection.area_ratio, config)
    detection.position_coef = position_coefficient(
        detection.center_x_norm, detection.center_y_norm, config
    )
    detection.contrast_coef = contrast_coefficient(detection, frame, config)
    detection.intensity = intensity(
        detection.area_coef, detection.position_coef, detection.contrast_coef
    )
