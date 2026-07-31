"""Pipeline data schemas."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .domain import (
    BrandStatus,
    ClassificationInputStatus,
    CropQualityStatus,
    FinalStatus,
)


@dataclass
class InputMetadata:
    source_path: Path
    input_type: str
    fps: float
    frame_count: int
    frame_stride: int
    delta_t_sec: float
    width: int
    height: int


@dataclass
class FrameRecord:
    frame_index: int
    timestamp_sec: float
    width: int
    height: int
    delta_t_sec: float
    image: np.ndarray = field(repr=False)


@dataclass
class DetectionRecord:
    run_id: str
    source_path: str
    input_type: str
    frame_index: int
    timestamp_sec: float
    sample_delta_t_sec: float
    det_index: int
    track_id: int | None
    det_class: str
    det_conf: float
    bbox_x1: float
    bbox_y1: float
    bbox_x2: float
    bbox_y2: float
    bbox_width: float
    bbox_height: float
    bbox_aspect_ratio: float
    bbox_area: float
    area_ratio: float
    center_x: float
    center_y: float
    center_x_norm: float
    center_y_norm: float
    object_id: int | None = None
    crop_path: str = ""
    crop_width: int = 0
    crop_height: int = 0
    crop_quality_status: CropQualityStatus = CropQualityStatus.REJECTED
    crop_quality_reason: str = "not_evaluated"
    crop_quality_score: float = 0.0
    classification_input_status: ClassificationInputStatus = (
        ClassificationInputStatus.REJECTED
    )
    classification_attempted: bool = False
    brand_pred: str = ""
    brand_conf: float = 0.0
    top1_brand: str = ""
    top1_score: float = 0.0
    top2_brand: str = ""
    top2_score: float = 0.0
    top3_brand: str = ""
    top3_score: float = 0.0
    area_coef: float = 1.0
    position_coef: float = 1.0
    contrast_coef: float = 1.0
    intensity: float = 0.0
    brand_status: BrandStatus = BrandStatus.NOT_CLASSIFIED
    final_status: FinalStatus = FinalStatus.NOT_CLASSIFIED
    business_brand: str = "other"
    business_visible: bool = False
    status_reason: str = "not_classified_no_valid_crop"

    @property
    def bbox_xyxy(self) -> tuple[float, float, float, float]:
        return (self.bbox_x1, self.bbox_y1, self.bbox_x2, self.bbox_y2)


@dataclass
class TrackRecord:
    run_id: str
    source_path: str
    track_id: int
    object_id: int
    first_frame_index: int
    last_frame_index: int
    first_timestamp_sec: float
    last_timestamp_sec: float
    visible_duration_sec: float
    detections_count: int
    best_crop_path: str
    best_timestamp_sec: float
    # Только физика S·α. Значимость β и итог V считает бэкенд из геозон.
    attention_seconds: float
    confidence_coef: float
    final_brand: str
    final_brand_conf: float
    final_status: FinalStatus
    business_brand: str
    business_visible: bool
    final_status_reason: str
    track_confirmed: bool
    manual_review_required: bool


DetectionMap = dict[int, list[DetectionRecord]]
