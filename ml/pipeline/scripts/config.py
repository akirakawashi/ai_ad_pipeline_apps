"""Pipeline configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PipelineConfig:
    project_root: Path
    input_path: Path
    output_dir: Path
    detector_model_path: Path
    classifier_model_path: Path
    brand_overrides_path: Path | None
    run_id: str

    frame_stride: int = 10
    detector_conf_min: float = 0.50
    detector_imgsz: int | None = 960
    detector_iou: float = 0.50
    device: str | None = None

    min_detection_width: int = 48
    min_detection_height: int = 40
    min_detection_area_ratio: float = 0.001
    min_detection_aspect_ratio: float = 0.25
    max_detection_aspect_ratio: float = 8.0

    min_classify_width: int = 120
    min_classify_height: int = 60
    min_classify_area_ratio: float = 0.002
    crop_margin_ratio: float = 0.05

    crop_quality_pass_min: float = 0.65
    crop_quality_borderline_min: float = 0.40
    blur_pass_variance: float = 120.0
    blur_borderline_variance: float = 35.0
    brightness_min: float = 35.0
    brightness_max: float = 225.0

    brand_conf_accept: float = 0.80
    other_conf_accept: float = 0.85
    manual_review_min: float = 0.40
    brand_conflict_margin: float = 0.10

    tracking_iou_min: float = 0.35
    max_track_gap_frames: int = 2
    min_track_detections: int = 2
    min_track_frame_span: int = 10
    best_crops_per_object: int = 3

    object_merge_max_gap_frames: int = 90
    object_merge_min_iou: float = 0.02
    object_merge_max_center_distance: float = 0.18
    object_merge_max_area_ratio: float = 5.0
    object_merge_max_aspect_ratio: float = 3.0

    business_min_object_detections: int = 3
    business_min_visible_duration_sec: float = 0.50
    render_gap_fill_max_sec: float = 0.35

    visibility_area_norm: float = 0.05
    min_position_weight: float = 0.20

    save_annotated_frames: bool = False


def default_project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def resolve_project_path(project_root: Path, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return project_root / path
