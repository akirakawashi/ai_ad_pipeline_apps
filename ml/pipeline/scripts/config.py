"""Pipeline configuration grouped by processing responsibility."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class DetectionConfig:
    confidence_min: float = 0.50
    image_size: int | None = 960
    iou: float = 0.50
    min_width: int = 48
    min_height: int = 40
    min_area_ratio: float = 0.001
    min_aspect_ratio: float = 0.25
    max_aspect_ratio: float = 8.0


@dataclass(frozen=True)
class CropQualityConfig:
    pass_min: float = 0.65
    borderline_min: float = 0.40
    blur_pass_variance: float = 120.0
    blur_borderline_variance: float = 35.0
    brightness_min: float = 35.0
    brightness_max: float = 225.0


@dataclass(frozen=True)
class ClassificationConfig:
    min_width: int = 120
    min_height: int = 60
    min_area_ratio: float = 0.002
    crop_margin_ratio: float = 0.05
    brand_confidence_accept: float = 0.80
    other_confidence_accept: float = 0.85
    manual_review_min: float = 0.40
    conflict_margin: float = 0.10
    best_crops_per_object: int = 3


@dataclass(frozen=True)
class TrackingConfig:
    iou_min: float = 0.35
    max_gap_frames: int = 2
    min_detections: int = 2
    min_frame_span: int = 10
    object_merge_max_gap_frames: int = 90
    object_merge_min_iou: float = 0.02
    object_merge_max_center_distance: float = 0.18
    object_merge_max_area_ratio: float = 5.0
    object_merge_max_aspect_ratio: float = 3.0


@dataclass(frozen=True)
class BusinessConfig:
    min_object_detections: int = 3
    min_visible_duration_sec: float = 0.50


@dataclass(frozen=True)
class VisibilityConfig:
    area_norm: float = 0.05
    min_position_weight: float = 0.20


@dataclass(frozen=True)
class RenderingConfig:
    gap_fill_max_sec: float = 0.35
    save_annotated_frames: bool = False


@dataclass(frozen=True)
class PipelineConfig:
    input_path: Path
    output_dir: Path
    detector_model_path: Path
    classifier_model_path: Path
    brand_overrides_path: Path | None
    run_id: str
    frame_stride: int = 10
    device: str | None = None
    detection: DetectionConfig = field(default_factory=DetectionConfig)
    crop_quality: CropQualityConfig = field(default_factory=CropQualityConfig)
    classification: ClassificationConfig = field(default_factory=ClassificationConfig)
    tracking: TrackingConfig = field(default_factory=TrackingConfig)
    business: BusinessConfig = field(default_factory=BusinessConfig)
    visibility: VisibilityConfig = field(default_factory=VisibilityConfig)
    rendering: RenderingConfig = field(default_factory=RenderingConfig)


def default_project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def resolve_project_path(project_root: Path, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return project_root / path
