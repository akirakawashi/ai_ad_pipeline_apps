"""Фактор площади A — насколько крупно объект в кадре (0…1).

Тир-таблица (доля кадра → коэффициент) с линейной интерполяцией между точками.
Таблица — в ScoringConfig.area, бизнес тюнит её без правки кода.
"""

from __future__ import annotations

from ..config import PipelineConfig
from .interpolation import piecewise_linear


def area_coefficient(area_ratio: float, config: PipelineConfig) -> float:
    return piecewise_linear(area_ratio, config.scoring.area.points)
