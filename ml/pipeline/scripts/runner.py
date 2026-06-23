"""Pipeline orchestration for a single local run."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from math import ceil
from pathlib import Path
from typing import Any, Protocol

from .aggregation import apply_track_results, build_tracks
from .classification import BrandClassifier, classify_detections, load_classifier
from .config import PipelineConfig
from .crops import copy_crops_by_status, save_detection_crops
from .detection import load_detector, run_detection
from .domain import ClassificationInputStatus, CropQualityStatus
from .html_viewer import write_html_overlay_viewer
from .io import iter_frames, load_frames, load_metadata
from .overrides import apply_brand_overrides
from .quality import evaluate_crop_quality
from .reports import write_pipeline_outputs
from .schemas import DetectionRecord, FrameRecord, InputMetadata, TrackRecord
from .track_groups import assign_object_groups, stabilize_object_brands
from .tracking import assign_track_ids
from .visualization import write_annotated_media

logger = logging.getLogger(__name__)


class PipelineProgressReporter(Protocol):
    def update(
        self,
        stage: str,
        progress: int,
        message: str | None = None,
    ) -> None: ...


class LoggingProgressReporter:
    def update(
        self,
        stage: str,
        progress: int,
        message: str | None = None,
    ) -> None:
        logger.info(
            "[%s%%] %s%s",
            progress,
            stage,
            f": {message}" if message else "",
        )


@dataclass(frozen=True)
class PipelineModels:
    detector: Any
    classifier: BrandClassifier | None = None


@dataclass
class PipelineContext:
    config: PipelineConfig
    metadata: InputMetadata
    frames: list[FrameRecord] | None
    detections: list[DetectionRecord]
    tracks: list[TrackRecord] = field(default_factory=list)


@dataclass(frozen=True)
class PipelineRunResult:
    output_dir: Path
    metadata: InputMetadata
    detections: list[DetectionRecord]
    tracks: list[TrackRecord]


def load_pipeline_models(
    config: PipelineConfig,
    *,
    include_classifier: bool = True,
) -> PipelineModels:
    """Load models for callers that want to reuse them across pipeline runs."""
    classifier = load_classifier(config) if include_classifier else None
    return PipelineModels(
        detector=load_detector(config),
        classifier=classifier,
    )


def run_pipeline(
    config: PipelineConfig,
    models: PipelineModels | None = None,
    progress_reporter: PipelineProgressReporter | None = None,
) -> PipelineRunResult:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    log_run_configuration(config)
    reporter = progress_reporter or LoggingProgressReporter()
    reporter.update("preparing", 1, "Подготовка моделей и входного видео")

    active_models = models or load_pipeline_models(
        config,
        include_classifier=False,
    )
    context = run_detection_stage(
        active_models.detector,
        config,
        progress_reporter=reporter,
    )
    logger.info("detections after gate: %s", len(context.detections))

    reporter.update("tracking", 66, "Связывание детекций в объекты")
    run_tracking_stage(context)
    reporter.update("classification", 71, "Классификация лучших crop")
    run_classification_stage(context, active_models)
    reporter.update("aggregation", 83, "Агрегация результатов")
    run_final_aggregation_stage(context)
    run_business_rules_stage(context)
    reporter.update("rendering", 88, "Формирование видео и отчётов")
    write_artifacts_stage(context)
    reporter.update(
        "uploading_artifacts",
        96,
        "Локальные артефакты готовы",
    )

    logger.info("tracks: %s", len(context.tracks))
    if context.metadata.input_type == "video":
        logger.info("viewer: %s", config.output_dir / "viewer.html")
    logger.info("report: %s", config.output_dir / "report.html")

    return PipelineRunResult(
        output_dir=config.output_dir,
        metadata=context.metadata,
        detections=context.detections,
        tracks=context.tracks,
    )


def log_run_configuration(config: PipelineConfig) -> None:
    logger.info("input: %s", config.input_path)
    logger.info("output: %s", config.output_dir)
    logger.info("detector: %s", config.detector_model_path)
    logger.info("classifier: %s", config.classifier_model_path)


def run_detection_stage(
    detector: Any,
    config: PipelineConfig,
    *,
    progress_reporter: PipelineProgressReporter | None = None,
) -> PipelineContext:
    metadata = load_metadata(config.input_path, config.frame_stride)
    if metadata.input_type == "video":
        detections = run_video_detection_stream(
            detector,
            metadata,
            config,
            progress_reporter=progress_reporter,
        )
        return PipelineContext(
            config=config,
            metadata=metadata,
            frames=None,
            detections=detections,
        )

    metadata, frames = load_frames(config.input_path, config.frame_stride)
    logger.info(
        "loaded frames: %s (%s, fps=%.3f)",
        len(frames),
        metadata.input_type,
        metadata.fps,
    )
    detections = run_detection(detector, frames, metadata, config)
    save_detection_crops(
        detections,
        {frame.frame_index: frame for frame in frames},
        config.output_dir / "crops" / "all",
        config,
    )
    evaluate_crop_quality(detections, config)
    if progress_reporter:
        progress_reporter.update(
            "detection",
            65,
            "Изображение обработано",
        )
    return PipelineContext(
        config=config,
        metadata=metadata,
        frames=frames,
        detections=detections,
    )


def run_tracking_stage(context: PipelineContext) -> None:
    assign_track_ids(context.detections, context.config)
    preliminary_tracks = build_tracks(context.detections, context.config)
    object_count = assign_object_groups(
        preliminary_tracks,
        context.detections,
        context.config,
    )
    logger.info("objects: %s", object_count)


def run_classification_stage(
    context: PipelineContext,
    models: PipelineModels,
) -> None:
    if not has_classification_candidates(context.detections):
        return
    classifier = models.classifier or load_classifier(context.config)
    classify_detections(
        classifier,
        context.detections,
        context.config,
    )


def has_classification_candidates(
    detections: list[DetectionRecord],
) -> bool:
    return any(
        detection.crop_quality_status
        in {CropQualityStatus.PASSED, CropQualityStatus.BORDERLINE}
        and detection.classification_input_status
        in {
            ClassificationInputStatus.ACCEPTED,
            ClassificationInputStatus.BORDERLINE,
        }
        for detection in detections
    )


def run_final_aggregation_stage(context: PipelineContext) -> None:
    context.tracks = build_tracks(context.detections, context.config)
    apply_track_results(context.tracks, context.detections)


def run_business_rules_stage(context: PipelineContext) -> None:
    applied_overrides = apply_brand_overrides(
        context.tracks,
        context.detections,
        context.config.brand_overrides_path,
    )
    if applied_overrides:
        logger.info("brand overrides applied: %s", applied_overrides)

    stabilized_tracks = stabilize_object_brands(
        context.tracks,
        context.detections,
        context.config,
    )
    if stabilized_tracks:
        logger.info(
            "tracks stabilized by object brand: %s",
            stabilized_tracks,
        )


def write_artifacts_stage(context: PipelineContext) -> None:
    tracks_by_id = {track.track_id: track for track in context.tracks}
    copy_crops_by_status(
        context.detections,
        tracks_by_id,
        context.config.output_dir / "crops",
    )
    write_annotated_media(
        context.config.output_dir,
        context.frames,
        context.detections,
        context.tracks,
        context.metadata,
        context.config,
    )
    write_html_overlay_viewer(
        context.config.output_dir,
        context.metadata,
        context.detections,
        context.tracks,
        context.config,
    )
    write_pipeline_outputs(
        context.config.output_dir,
        context.metadata,
        context.detections,
        context.tracks,
    )


def run_video_detection_stream(
    detector: Any,
    metadata: InputMetadata,
    config: PipelineConfig,
    *,
    progress_reporter: PipelineProgressReporter | None = None,
) -> list[DetectionRecord]:
    detections: list[DetectionRecord] = []
    crops_dir = config.output_dir / "crops" / "all"
    processed_frames = 0
    sampled_frame_count = max(
        1,
        ceil(metadata.frame_count / max(1, metadata.frame_stride)),
    )

    logger.info(
        "streaming video frames: stride=%s, fps=%.3f",
        metadata.frame_stride,
        metadata.fps,
    )
    for frame in iter_frames(config.input_path, config.frame_stride):
        frame_detections = run_detection(detector, [frame], metadata, config)
        save_detection_crops(
            frame_detections,
            {frame.frame_index: frame},
            crops_dir,
            config,
        )
        evaluate_crop_quality(frame_detections, config)
        detections.extend(frame_detections)

        processed_frames += 1
        if progress_reporter and (
            processed_frames == 1 or processed_frames % 25 == 0
        ):
            detection_progress = 2 + round(
                63 * min(1.0, processed_frames / sampled_frame_count)
            )
            progress_reporter.update(
                "detection",
                detection_progress,
                (
                    f"Обработано кадров: {processed_frames}"
                    f" из {sampled_frame_count}"
                ),
            )
        if processed_frames % 100 == 0:
            logger.info(
                "processed sampled frames: %s, detections after gate: %s",
                processed_frames,
                len(detections),
            )

    if processed_frames == 0:
        raise RuntimeError(f"No frames were read from video: {config.input_path}")
    logger.info(
        "processed sampled frames: %s (%s, fps=%.3f)",
        processed_frames,
        metadata.input_type,
        metadata.fps,
    )
    if progress_reporter:
        progress_reporter.update(
            "detection",
            65,
            f"Обработано кадров: {processed_frames}",
        )
    return detections
