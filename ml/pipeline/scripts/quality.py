"""Crop quality gate helpers."""

from __future__ import annotations

import cv2

from .config import PipelineConfig
from .domain import (
    BrandStatus,
    ClassificationInputStatus,
    CropQualityStatus,
    FinalStatus,
)
from .schemas import DetectionRecord


def evaluate_crop_quality(
    detections: list[DetectionRecord], config: PipelineConfig
) -> None:
    for detection in detections:
        _evaluate_one(detection, config)


def _evaluate_one(detection: DetectionRecord, config: PipelineConfig) -> None:
    if not detection.crop_path:
        _reject(detection, "missing_crop", 0.0)
        return

    if (
        detection.crop_width < config.classification.min_width
        or detection.crop_height < config.classification.min_height
        or detection.area_ratio < config.classification.min_area_ratio
    ):
        _reject(detection, "small_crop_in_video", 0.0)
        return

    image = cv2.imread(detection.crop_path, cv2.IMREAD_COLOR)
    if image is None:
        _reject(detection, "missing_crop", 0.0)
        return

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(gray.mean())

    blur_score = _blur_score(blur_var, config)
    brightness_score, video_quality_reason = _brightness_score(brightness, config)
    size_score = min(
        1.0,
        detection.area_ratio / max(1e-9, config.classification.min_area_ratio * 3),
    )
    detector_score = min(
        1.0,
        detection.det_conf / max(1e-9, config.detection.confidence_min * 2),
    )

    score = max(
        0.0,
        min(
            1.0,
            0.35 * size_score
            + 0.30 * blur_score
            + 0.20 * brightness_score
            + 0.15 * detector_score,
        ),
    )

    reason = "ok"
    if blur_var < config.crop_quality.blur_borderline_variance:
        reason = "motion_blur_in_video"
    elif video_quality_reason != "ok":
        reason = video_quality_reason
    elif detection.crop_quality_reason == "clipped_by_frame_border":
        reason = "clipped_by_frame_border"

    detection.crop_quality_score = score
    detection.crop_quality_reason = reason
    if score >= config.crop_quality.pass_min:
        detection.crop_quality_status = CropQualityStatus.PASSED
        detection.classification_input_status = ClassificationInputStatus.ACCEPTED
    elif score >= config.crop_quality.borderline_min:
        detection.crop_quality_status = CropQualityStatus.BORDERLINE
        detection.classification_input_status = ClassificationInputStatus.BORDERLINE
    else:
        detection.crop_quality_status = CropQualityStatus.REJECTED
        detection.classification_input_status = ClassificationInputStatus.REJECTED
        detection.brand_status = BrandStatus.NOT_CLASSIFIED
        detection.final_status = FinalStatus.NOT_CLASSIFIED
        detection.status_reason = reason if reason != "ok" else "low_video_quality"
        if reason == "ok":
            detection.crop_quality_reason = "low_video_quality"


def _reject(detection: DetectionRecord, reason: str, score: float) -> None:
    detection.crop_quality_status = CropQualityStatus.REJECTED
    detection.crop_quality_reason = reason
    detection.crop_quality_score = score
    detection.classification_input_status = ClassificationInputStatus.REJECTED
    detection.classification_attempted = False
    detection.brand_status = BrandStatus.NOT_CLASSIFIED
    detection.final_status = FinalStatus.NOT_CLASSIFIED
    detection.status_reason = reason


def _blur_score(blur_var: float, config: PipelineConfig) -> float:
    if blur_var <= config.crop_quality.blur_borderline_variance:
        return 0.0
    if blur_var >= config.crop_quality.blur_pass_variance:
        return 1.0
    span = (
        config.crop_quality.blur_pass_variance
        - config.crop_quality.blur_borderline_variance
    )
    return (blur_var - config.crop_quality.blur_borderline_variance) / max(1e-9, span)


def _brightness_score(brightness: float, config: PipelineConfig) -> tuple[float, str]:
    if brightness < config.crop_quality.brightness_min:
        return max(
            0.0, brightness / max(1e-9, config.crop_quality.brightness_min)
        ), "low_video_quality"
    if brightness > config.crop_quality.brightness_max:
        excess = brightness - config.crop_quality.brightness_max
        return max(
            0.0,
            1.0 - excess / max(1e-9, 255 - config.crop_quality.brightness_max),
        ), "low_video_quality"
    return 1.0, "ok"
