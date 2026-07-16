from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from domain.entities import PipelineArtifactType, PipelineRunStage, PipelineRunStatus
from pipeline_contracts.artifacts import (
    BrandTrackSummaryRow,
    OverlayDisplayPayload,
    OverlayFramePayload,
    OverlayObjectPayload,
    OverlayPayload,
    OverlayVideoPayload,
    TrackCsvRow,
)


class ApplicationDTO(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )


class UploadTargetDTO(ApplicationDTO):
    method: str
    url: str
    headers: dict[str, str]


# Ref-DTO живут здесь, а не в catalog.py: PipelineRunDTO ссылается на пачку,
# а catalog.py импортирует ApplicationDTO отсюда — иначе получился бы цикл.
class CityRefDTO(ApplicationDTO):
    id: str
    slug: str
    name: str


class RouteRefDTO(ApplicationDTO):
    id: str
    slug: str
    name: str
    color_hex: str | None = None


class RunBatchRefDTO(ApplicationDTO):
    batch_id: str
    sequence_number: int
    title: str
    route: RouteRefDTO
    city: CityRefDTO


class PipelineArtifactDTO(ApplicationDTO):
    id: str
    run_id: str
    artifact_type: PipelineArtifactType
    object_key: str
    content_type: str
    size_bytes: int
    created_at: datetime | None


class PipelineRunEventDTO(ApplicationDTO):
    id: str
    run_id: str
    stage: PipelineRunStage
    progress: int = Field(ge=0, le=100)
    message: str | None
    created_at: datetime | None


class PipelineRunDTO(ApplicationDTO):
    run_id: str
    source_name: str
    source_object_key: str
    source_content_type: str | None
    source_size_bytes: int
    status: PipelineRunStatus
    stage: PipelineRunStage
    progress: int = Field(ge=0, le=100)
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
    # Заполняется только там, где связь загружена явно (_run_to_dto(with_batch=...)).
    # None означает «Без маршрута» либо «связь не запрашивали».
    batch: RunBatchRefDTO | None = None
    artifacts: list[PipelineArtifactDTO] = Field(default_factory=list)
    events: list[PipelineRunEventDTO] = Field(default_factory=list)


class CreateRunDTO(ApplicationDTO):
    run_id: str
    status: PipelineRunStatus
    upload: UploadTargetDTO


class PaginatedRunsDTO(ApplicationDTO):
    items: list[PipelineRunDTO]
    page: int
    page_size: int
    total: int


class ArtifactUrlDTO(ApplicationDTO):
    artifact_id: str
    url: str


class PlaybackDTO(ApplicationDTO):
    source_url: str | None
    annotated_url: str | None


class BrandSummaryDTO(BrandTrackSummaryRow):
    pass


class RunSummaryTotalsDTO(ApplicationDTO):
    total_objects: int
    visibility_index: float


class RunSummaryDTO(ApplicationDTO):
    run: PipelineRunDTO
    totals: RunSummaryTotalsDTO
    brands: list[BrandSummaryDTO]


class RunObjectDTO(TrackCsvRow):
    crop_url: str | None = None


class RunObjectsDTO(ApplicationDTO):
    run_id: str
    objects: list[RunObjectDTO]


class RunTimelinePointDTO(ApplicationDTO):
    bucket_start_sec: float
    business_brand: str | None
    detection_count: int
    visibility_score: float


class RunTimelineDTO(ApplicationDTO):
    run_id: str
    bucket_seconds: int
    points: list[RunTimelinePointDTO]


class OverlayVideoDTO(OverlayVideoPayload):
    pass


class OverlayDisplayDTO(OverlayDisplayPayload):
    pass


class OverlayObjectDTO(OverlayObjectPayload):
    pass


class OverlayFrameDTO(OverlayFramePayload):
    pass


class OverlayPayloadDTO(OverlayPayload):
    pass
