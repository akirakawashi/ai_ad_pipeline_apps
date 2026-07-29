from __future__ import annotations

from enum import StrEnum
from pathlib import Path


class PipelineRunStatus(StrEnum):
    UPLOADING = "uploading"
    UPLOAD_FAILED = "upload_failed"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    PROCESSING_FAILED = "processing_failed"


class PipelineRunStage(StrEnum):
    UPLOAD = "upload"
    QUEUED = "queued"
    PREPARING = "preparing"
    DETECTION = "detection"
    TRACKING = "tracking"
    CLASSIFICATION = "classification"
    AGGREGATION = "aggregation"
    RENDERING = "rendering"
    UPLOADING_ARTIFACTS = "uploading_artifacts"
    COMPLETED = "completed"
    FAILED = "failed"


class PipelineArtifactType(StrEnum):
    SOURCE_VIDEO = "source_video"
    INPUT_METADATA = "input_metadata"
    OVERLAY = "overlay"
    DETECTIONS = "detections"
    TRACKS = "tracks"
    BRAND_SUMMARY = "brand_summary"
    DETECTION_SUMMARY = "detection_summary"
    FRAME_SUMMARY = "frame_summary"
    REPORT = "report"
    VIEWER = "viewer"
    CROP = "crop"
    ARTIFACT = "artifact"


PIPELINE_ARTIFACT_TYPES_BY_FILE_NAME: dict[str, PipelineArtifactType] = {
    "input_meta.json": PipelineArtifactType.INPUT_METADATA,
    "overlay.json": PipelineArtifactType.OVERLAY,
    "detections.csv": PipelineArtifactType.DETECTIONS,
    "tracks.csv": PipelineArtifactType.TRACKS,
    "brand_summary_by_tracks.csv": PipelineArtifactType.BRAND_SUMMARY,
    "brand_summary_by_detections.csv": PipelineArtifactType.DETECTION_SUMMARY,
    "frame_summary.csv": PipelineArtifactType.FRAME_SUMMARY,
    "report.html": PipelineArtifactType.REPORT,
    "viewer.html": PipelineArtifactType.VIEWER,
}


def artifact_type_for_path(relative_path: Path) -> PipelineArtifactType:
    if relative_path.parts[:1] == ("crops",):
        return PipelineArtifactType.CROP
    return PIPELINE_ARTIFACT_TYPES_BY_FILE_NAME.get(
        relative_path.name,
        PipelineArtifactType.ARTIFACT,
    )


def should_register_artifact(relative_path: Path) -> bool:
    return relative_path.parts[:1] != ("crops",)
