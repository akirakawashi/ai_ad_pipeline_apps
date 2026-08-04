from __future__ import annotations

from enum import StrEnum
from pathlib import Path


class PipelineRunStatus(StrEnum):
    UPLOADING = "uploading"
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
    REPORT = "report"
    VIEWER = "viewer"
    ARTIFACT = "artifact"


PIPELINE_ARTIFACT_TYPES_BY_FILE_NAME: dict[str, PipelineArtifactType] = {
    "input_meta.json": PipelineArtifactType.INPUT_METADATA,
    "overlay.json": PipelineArtifactType.OVERLAY,
    "detections.csv": PipelineArtifactType.DETECTIONS,
    "tracks.csv": PipelineArtifactType.TRACKS,
    "report.html": PipelineArtifactType.REPORT,
    "viewer.html": PipelineArtifactType.VIEWER,
}


def artifact_type_for_path(relative_path: Path) -> PipelineArtifactType:
    return PIPELINE_ARTIFACT_TYPES_BY_FILE_NAME.get(
        relative_path.name,
        PipelineArtifactType.ARTIFACT,
    )


def should_register_artifact(relative_path: Path) -> bool:
    return relative_path.parts[:1] != ("crops",)
