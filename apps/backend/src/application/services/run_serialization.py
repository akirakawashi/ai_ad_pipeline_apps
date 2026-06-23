from __future__ import annotations

from infrastructure.database.models import (
    PipelineArtifactModel,
    PipelineRunEventModel,
    PipelineRunModel,
)


def artifact_to_dict(artifact: PipelineArtifactModel) -> dict:
    return {
        "id": artifact.id,
        "artifact_type": artifact.artifact_type,
        "object_key": artifact.object_key,
        "content_type": artifact.content_type,
        "size_bytes": artifact.size_bytes,
        "created_at": artifact.created_at,
    }


def event_to_dict(event: PipelineRunEventModel) -> dict:
    return {
        "id": event.id,
        "stage": event.stage,
        "progress": event.progress,
        "message": event.message,
        "created_at": event.created_at,
    }


def run_to_dict(
    run: PipelineRunModel,
    *,
    include_artifacts: bool = False,
    include_events: bool = False,
) -> dict:
    result = {
        "run_id": run.id,
        "source_name": run.source_name,
        "source_content_type": run.source_content_type,
        "source_size_bytes": run.source_size_bytes,
        "status": run.status,
        "stage": run.stage,
        "progress": run.progress,
        "status_message": run.status_message,
        "error_code": run.error_code,
        "error_message": run.error_message,
        "fps": run.fps,
        "frame_count": run.frame_count,
        "frame_stride": run.frame_stride,
        "duration_sec": run.duration_sec,
        "width": run.width,
        "height": run.height,
        "created_at": run.created_at,
        "upload_completed_at": run.upload_completed_at,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "updated_at": run.updated_at,
    }
    if include_artifacts:
        result["artifacts"] = [
            artifact_to_dict(artifact) for artifact in run.artifacts
        ]
    if include_events:
        result["events"] = [event_to_dict(event) for event in run.events]
    return result
