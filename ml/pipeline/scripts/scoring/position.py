"""Фактор положения и стороны движения P (0…1).

v1: горизонталь (экран-X) с учётом стороны движения. Своя (попутная) сторона
весит больше встречной, пик — у центра на своей стороне. Кривая — в
ScoringConfig.position, бизнес тюнит без правки кода.
Высоту (center_y_norm) в v1 не учитываем (задел на будущее в сигнатуре).
"""

from __future__ import annotations

from ..config import PipelineConfig
from .interpolation import piecewise_linear


def position_coefficient(
    center_x_norm: float, center_y_norm: float, config: PipelineConfig
) -> float:
    # Кривая задана для правостороннего движения (своя сторона = справа).
    # Для левостороннего зеркалим экран-X, чтобы «своя сторона» была слева.
    x = center_x_norm if config.scoring.handedness == "right" else 1.0 - center_x_norm
    return piecewise_linear(x, config.scoring.position.points)
