"""Секунды внимания объекта: S = Σ (I · Δt) по всем его кадрам.

Время — ось интегрирования (Δt = sample_delta_t_sec), не отдельный множитель.
"""

from __future__ import annotations

from collections.abc import Iterable

from ..schemas import DetectionRecord


def attention_seconds(detections: Iterable[DetectionRecord]) -> float:
    return sum(
        detection.intensity * detection.sample_delta_t_sec for detection in detections
    )
