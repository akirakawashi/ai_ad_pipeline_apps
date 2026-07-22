"""Коэффициент значимости точки β — внешний вес места (гео).

ЗАГЛУШКА: β = 1.0, пока нет гео-данных.
Провайдер «координата → коэффициент» на слое трафика — Фаза 2 (Шаги 8–9).
"""

from __future__ import annotations

from collections.abc import Iterable

from ..config import PipelineConfig
from ..schemas import DetectionRecord


def significance_coefficient(
    detections: Iterable[DetectionRecord],
    config: PipelineConfig,
) -> float:
    return 1.0
