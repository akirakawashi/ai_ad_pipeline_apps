from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field


T = TypeVar("T")


class OkResponse(BaseModel, Generic[T]):
    data: T


class ErrorResponse(BaseModel):
    detail: str


class PipelineRunResponse(BaseModel):
    run_id: str
    source_name: str | None = None
    source_path: str | None = None
    input_type: str | None = None
    fps: float | None = None
    frame_count: int | None = None
    frame_stride: int | None = None
    duration_sec: float | None = None
    width: int | None = None
    height: int | None = None
    created_at: float
    has_overlay: bool
    has_viewer: bool
    has_report: bool
    has_annotated_video: bool


class RunArtifactResponse(BaseModel):
    name: str
    relative_path: str
    media_type: str
    size_bytes: int


class RunSummaryResponse(BaseModel):
    run: PipelineRunResponse
    totals: dict[str, Any]
    brands: list[dict[str, Any]]
    artifacts: list[RunArtifactResponse]


class RunObjectsResponse(BaseModel):
    run_id: str
    objects: list[dict[str, Any]]


class RunTimelineResponse(BaseModel):
    run_id: str
    bucket_seconds: int = Field(ge=1, le=300)
    points: list[dict[str, Any]]

