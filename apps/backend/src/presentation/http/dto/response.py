from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field


T = TypeVar("T")


class OkResponse(BaseModel, Generic[T]):
    data: T


class ErrorResponse(BaseModel):
    detail: str


class UploadTargetResponse(BaseModel):
    method: str
    url: str
    headers: dict[str, str]


class CreateRunRequest(BaseModel):
    file_name: str = Field(min_length=1, max_length=512)
    content_type: str | None = Field(default=None, max_length=255)
    size_bytes: int = Field(gt=0)


class CreateRunResponse(BaseModel):
    run_id: str
    status: str
    upload: UploadTargetResponse


class RunArtifactResponse(BaseModel):
    id: str
    artifact_type: str
    object_key: str
    content_type: str
    size_bytes: int
    created_at: datetime


class RunEventResponse(BaseModel):
    id: str
    stage: str
    progress: int
    message: str | None
    created_at: datetime


class PipelineRunResponse(BaseModel):
    run_id: str
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


class PaginatedRunsResponse(BaseModel):
    items: list[PipelineRunResponse]
    page: int
    page_size: int
    total: int


class RunSummaryResponse(BaseModel):
    run: PipelineRunResponse
    totals: dict[str, Any]
    brands: list[dict[str, Any]]


class RunObjectsResponse(BaseModel):
    run_id: str
    objects: list[dict[str, Any]]


class RunTimelineResponse(BaseModel):
    run_id: str
    bucket_seconds: int
    points: list[dict[str, Any]]


class ArtifactUrlResponse(BaseModel):
    artifact_id: str
    url: str


class PlaybackResponse(BaseModel):
    source_url: str | None
    annotated_url: str | None
