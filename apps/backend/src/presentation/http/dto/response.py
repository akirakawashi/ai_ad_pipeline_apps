from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field


T = TypeVar("T")


class ApiModel(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )


class OkResponse(ApiModel, Generic[T]):
    data: T


class ErrorResponse(ApiModel):
    detail: str


class UploadTargetResponse(ApiModel):
    method: str
    url: str
    headers: dict[str, str]


class CreateRunRequest(ApiModel):
    file_name: str = Field(min_length=1, max_length=512)
    content_type: str | None = Field(default=None, max_length=255)
    size_bytes: int = Field(gt=0)


class CreateRunResponse(ApiModel):
    run_id: str
    status: str
    upload: UploadTargetResponse


class RunArtifactResponse(ApiModel):
    id: str = Field(validation_alias="pipeline_artifacts_id")
    artifact_type: str
    object_key: str
    content_type: str
    size_bytes: int
    created_at: datetime


class RunEventResponse(ApiModel):
    id: str = Field(validation_alias="pipeline_run_events_id")
    stage: str
    progress: int
    message: str | None
    created_at: datetime


class PipelineRunResponse(ApiModel):
    run_id: str = Field(validation_alias="pipeline_runs_id")
    source_name: str
    source_content_type: str | None
    source_size_bytes: int
    status: str
    stage: str
    progress: int
    status_message: str | None
    error_code: str | None
    error_message: str | None
    fps: float | None
    frame_count: int | None
    frame_stride: int | None
    duration_sec: float | None
    width: int | None
    height: int | None
    created_at: datetime
    upload_completed_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime
    artifacts: list[RunArtifactResponse] = Field(default_factory=list)
    events: list[RunEventResponse] = Field(default_factory=list)


class PaginatedRunsResponse(ApiModel):
    items: list[PipelineRunResponse]
    page: int
    page_size: int
    total: int


class RunSummaryResponse(ApiModel):
    run: PipelineRunResponse
    totals: dict[str, Any]
    brands: list[dict[str, Any]]


class RunObjectsResponse(ApiModel):
    run_id: str
    objects: list[dict[str, Any]]


class RunTimelineResponse(ApiModel):
    run_id: str
    bucket_seconds: int
    points: list[dict[str, Any]]


class ArtifactUrlResponse(ApiModel):
    artifact_id: str
    url: str


class PlaybackResponse(ApiModel):
    source_url: str | None
    annotated_url: str | None
