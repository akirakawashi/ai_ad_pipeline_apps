from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from application.common.dto import (
    ArtifactUrlDTO,
    BatchStatusCountsDTO,
    BatchTotalsDTO,
    BrandSummaryDTO,
    CityDetailDTO,
    CityDTO,
    CityRefDTO,
    OverlayPayloadDTO,
    PlaybackDTO,
    RouteBatchDTO,
    RouteDTO,
    RouteRefDTO,
    RunBatchRefDTO,
    RunObjectDTO,
    RunSummaryTotalsDTO,
    RunTimelinePointDTO,
)
from domain.entities import PipelineArtifactType, PipelineRunStage, PipelineRunStatus


T = TypeVar("T")


class ApiModel(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )


class OkResponse(ApiModel, Generic[T]):
    data: T


class UploadTargetResponse(ApiModel):
    method: str
    url: str
    headers: dict[str, str]


class CreateRunRequest(ApiModel):
    file_name: str = Field(min_length=1, max_length=512)
    content_type: str | None = Field(default=None, max_length=255)
    size_bytes: int = Field(gt=0)
    # None означает «Без маршрута» — видео вне города и маршрута.
    batch_id: str | None = Field(default=None, max_length=36)


class CreateRunResponse(ApiModel):
    run_id: str
    status: PipelineRunStatus
    upload: UploadTargetResponse


class RunArtifactResponse(ApiModel):
    id: str = Field(validation_alias=AliasChoices("id", "pipeline_artifacts_id"))
    artifact_type: PipelineArtifactType
    object_key: str
    content_type: str
    size_bytes: int
    created_at: datetime | None


class RunEventResponse(ApiModel):
    id: str = Field(validation_alias=AliasChoices("id", "pipeline_run_events_id"))
    stage: PipelineRunStage
    progress: int
    message: str | None
    created_at: datetime | None


class CityRefResponse(CityRefDTO):
    pass


class RouteRefResponse(RouteRefDTO):
    pass


class RunBatchRefResponse(RunBatchRefDTO):
    pass


class RouteResponse(RouteDTO):
    pass


class CityResponse(CityDTO):
    pass


class CityDetailResponse(CityDetailDTO):
    pass


class BatchStatusCountsResponse(BatchStatusCountsDTO):
    pass


class BatchResponse(RouteBatchDTO):
    pass


class PaginatedBatchesResponse(ApiModel):
    items: list[BatchResponse]
    page: int
    page_size: int
    total: int


class BatchTotalsResponse(BatchTotalsDTO):
    pass


class BatchSummaryResponse(ApiModel):
    batch: BatchResponse
    totals: BatchTotalsResponse
    brands: list["BrandSummaryResponse"] = Field(default_factory=list)


class PipelineRunResponse(ApiModel):
    run_id: str = Field(validation_alias=AliasChoices("run_id", "pipeline_runs_id"))
    source_name: str
    source_content_type: str | None
    source_size_bytes: int
    status: PipelineRunStatus
    stage: PipelineRunStage
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
    created_at: datetime | None
    upload_completed_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime | None
    batch: RunBatchRefResponse | None = None
    artifacts: list[RunArtifactResponse] = Field(default_factory=list)
    events: list[RunEventResponse] = Field(default_factory=list)


class PaginatedRunsResponse(ApiModel):
    items: list[PipelineRunResponse]
    page: int
    page_size: int
    total: int


class BrandSummaryResponse(BrandSummaryDTO):
    pass


class RunSummaryTotalsResponse(RunSummaryTotalsDTO):
    pass


class RunSummaryResponse(ApiModel):
    run: PipelineRunResponse
    totals: RunSummaryTotalsResponse
    brands: list[BrandSummaryResponse]


class RunObjectResponse(RunObjectDTO):
    pass


class RunObjectsResponse(ApiModel):
    run_id: str
    objects: list[RunObjectResponse]


class RunTimelinePointResponse(RunTimelinePointDTO):
    pass


class RunTimelineResponse(ApiModel):
    run_id: str
    bucket_seconds: int
    points: list[RunTimelinePointResponse]


class ArtifactUrlResponse(ArtifactUrlDTO):
    pass


class PlaybackResponse(PlaybackDTO):
    pass


class OverlayPayloadResponse(OverlayPayloadDTO):
    pass
