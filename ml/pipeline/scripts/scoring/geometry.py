"""Геометрия детекции: центр bbox в пикселях и в долях кадра.

Инфраструктура (не скоринг): используется трекингом, склейкой объектов и
фактором положения. Раньше жила в visibility.py.
"""

from __future__ import annotations

from ..schemas import DetectionRecord, FrameRecord


def fill_geometry(detection: DetectionRecord, frame: FrameRecord) -> None:
    detection.center_x = (detection.bbox_x1 + detection.bbox_x2) / 2.0
    detection.center_y = (detection.bbox_y1 + detection.bbox_y2) / 2.0
    detection.center_x_norm = detection.center_x / max(1, frame.width)
    detection.center_y_norm = detection.center_y / max(1, frame.height)
