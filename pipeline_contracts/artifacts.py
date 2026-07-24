from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from pipeline_contracts.domain import (
    BrandStatus,
    ClassificationInputStatus,
    CropQualityStatus,
    FinalStatus,
)


class ArtifactModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class InputMetadataJson(ArtifactModel):
    source_path: str
    input_type: str
    fps: float
    frame_count: int
    frame_stride: int
    delta_t_sec: float
    width: int
    height: int


class DetectionCsvRow(ArtifactModel):
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
    object_id: int | None
    crop_path: str
    crop_width: int
    crop_height: int
    crop_quality_status: CropQualityStatus
    crop_quality_reason: str
    crop_quality_score: float
    classification_input_status: ClassificationInputStatus
    classification_attempted: bool
    brand_pred: str
    brand_conf: float
    top1_brand: str
    top1_score: float
    top2_brand: str
    top2_score: float
    top3_brand: str
    top3_score: float
    area_coef: float
    position_coef: float
    contrast_coef: float
    intensity: float
    brand_status: BrandStatus
    final_status: FinalStatus
    business_brand: str
    business_visible: bool
    status_reason: str

    def to_csv_row(self) -> dict[str, Any]:
        row = self.model_dump(mode="json")
        row["track_id"] = "" if self.track_id is None else self.track_id
        row["object_id"] = "" if self.object_id is None else self.object_id
        row["classification_attempted"] = int(self.classification_attempted)
        row["business_visible"] = int(self.business_visible)
        return row


class TrackCsvRow(ArtifactModel):
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
    # S и α — физика заметности. Значимость места β и итог V = S·α·β считает
    # бэкенд из геозон маршрута на лету: в артефакте их больше нет.
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

    def to_csv_row(self) -> dict[str, Any]:
        row = self.model_dump(mode="json")
        row["manual_review_required"] = int(self.manual_review_required)
        row["track_confirmed"] = int(self.track_confirmed)
        row["business_visible"] = int(self.business_visible)
        return row


class BrandDetectionSummaryRow(ArtifactModel):
    brand: str
    detection_count: int
    mean_brand_conf: float
    max_brand_conf: float
    first_timestamp_sec: float
    last_timestamp_sec: float
    sum_intensity: float


class FrameSummaryRow(ArtifactModel):
    frame_index: int
    timestamp_sec: float
    detections_total: int
    mts_count: int
    plus7_count: int
    miranda_count: int
    other_count: int
    sum_intensity: float


class BrandTrackSummaryRow(ArtifactModel):
    brand: str | None = None
    object_count: int = 0
    track_fragment_count: int | None = None
    sum_visibility_value: float | None = None
    sum_attention_seconds: float | None = None
    mean_final_brand_conf: float | None = None
    max_final_brand_conf: float | None = None
    first_timestamp_sec: float | None = None
    last_timestamp_sec: float | None = None


DETECTION_CSV_FIELDS = list(DetectionCsvRow.model_fields)
TRACK_CSV_FIELDS = list(TrackCsvRow.model_fields)
BRAND_DETECTION_SUMMARY_FIELDS = list(BrandDetectionSummaryRow.model_fields)
FRAME_SUMMARY_FIELDS = list(FrameSummaryRow.model_fields)
BRAND_TRACK_SUMMARY_FIELDS = list(BrandTrackSummaryRow.model_fields)


class OverlayVideoPayload(ArtifactModel):
    source: str
    width: int
    height: int
    fps: float
    frame_count: int
    frame_stride: int


class OverlayDisplayPayload(ArtifactModel):
    max_cards_per_frame: int
    fields: list[str]


class OverlayObjectPayload(ArtifactModel):
    object_id: int | None
    track_id: int | None
    brand: str
    label: str
    color: str
    bbox: tuple[float, float, float, float]
    det_conf: float
    brand_conf: float
    area_ratio: float
    intensity: float
    visibility_value: float
    card_priority: float


class OverlayFramePayload(ArtifactModel):
    frame_index: int
    timestamp_sec: float
    objects: list[OverlayObjectPayload]


class OverlayPayload(ArtifactModel):
    version: int
    video: OverlayVideoPayload
    display: OverlayDisplayPayload
    frames: list[OverlayFramePayload]
