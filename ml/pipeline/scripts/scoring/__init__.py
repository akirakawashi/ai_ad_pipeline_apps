"""Слой расчёта метрики заметности (физика).

Извлечение признаков (area / position / contrast / …) и сборка секунд внимания.
Пайплайн доходит до S·α; значимость места β и итог V = S·α·β считает бэкенд из
геозон маршрута — здесь их нет. Формулы:
    I = A · P · C            (на кадр)
    S = Σ (I · Δt)           (на объект — секунды внимания)
    α = confidence           (уверенность классификации)
"""

from __future__ import annotations

from ..config import PipelineConfig
from ..schemas import DetectionRecord, FrameRecord
from .area import area_coefficient
from .attention import attention_seconds
from .confidence import confidence_coefficient
from .contrast import contrast_coefficient
from .geometry import fill_geometry
from .intensity import intensity
from .position import position_coefficient

__all__ = [
    "area_coefficient",
    "attention_seconds",
    "confidence_coefficient",
    "contrast_coefficient",
    "fill_detection_scoring",
    "fill_geometry",
    "intensity",
    "position_coefficient",
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
