from __future__ import annotations

from datetime import datetime

from pipeline_contracts.artifacts import (
    OverlayDisplayPayload,
    OverlayFramePayload,
    OverlayObjectPayload,
    OverlayPayload,
    OverlayVideoPayload,
)
from pydantic import Field

from application.common.dto.base import ApplicationDTO
from application.common.dto.users import UserDTO
from domain.entities import PipelineArtifactType, PipelineRunStage, PipelineRunStatus


class UploadTargetDTO(ApplicationDTO):
    method: str
    url: str
    headers: dict[str, str]


# Ref-DTO живут здесь, а не в catalog.py: PipelineRunDTO ссылается на задание,
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


class RunAssignmentRefDTO(ApplicationDTO):
    assignment_id: str
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
    # --- реквизиты съёмки ---------------------------------------------------
    # Не путать со started_at / completed_at выше: те про обработку видео.
    shot_started_at: datetime
    # Не хранится: shot_started_at + duration_sec. None, пока нет длительности.
    shot_finished_at: datetime | None = None
    # Заполняются только там, где связи загружены явно (_run_to_dto(with_refs=...)).
    # None означает «связь не запрашивали», и только это: задание у съёмки есть
    # всегда — колонка обязательная. Поле остаётся необязательным именно ради
    # такого ответа: так отдают воркер и `GET /assignments/{id}/runs`.
    assignment: RunAssignmentRefDTO | None = None
    uploaded_by: UserDTO | None = None
    # Артефакты нужны самому бэкенду, а не браузеру: из них берутся ключи
    # tracks.csv, detections.csv, overlay.json и исходного видео. В ответ они
    # не уезжают — читать их в интерфейсе нечем и незачем.
    artifacts: list[PipelineArtifactDTO] = Field(default_factory=list)


class CreateRunDTO(ApplicationDTO):
    run_id: str
    status: PipelineRunStatus
    upload: UploadTargetDTO


class PaginatedRunsDTO(ApplicationDTO):
    items: list[PipelineRunDTO]
    page: int
    page_size: int
    total: int


class PlaybackDTO(ApplicationDTO):
    source_url: str | None


class BrandSummaryDTO(ApplicationDTO):
    brand: str
    object_count: int
    sum_visibility_value: float
    mean_final_brand_conf: float


class DwhVideoMetricInputDTO(ApplicationDTO):
    """Готовый брендовый итог съёмки перед append-only публикацией в DWH."""

    run_id: str
    city_id: str
    city_name: str
    route_id: str
    route_name: str
    assignment_id: str
    assignment_name: str
    brand: str | None
    sum_visibility_value: float | None
    is_active: bool = True


class RunSummaryTotalsDTO(ApplicationDTO):
    total_objects: int


class RunSummaryDTO(ApplicationDTO):
    run: PipelineRunDTO
    totals: RunSummaryTotalsDTO
    brands: list[BrandSummaryDTO]


class RunObjectDTO(ApplicationDTO):
    """Публичная карточка объекта, а не копия внутренней строки tracks.csv."""

    object_id: int
    track_id: int
    business_brand: str
    final_brand_conf: float
    visibility_value: float
    best_timestamp_sec: float
    crop_url: str | None = None


class RunObjectsDTO(ApplicationDTO):
    run_id: str
    objects: list[RunObjectDTO]


class RunTimelinePointDTO(ApplicationDTO):
    bucket_start_sec: float
    business_brand: str | None
    intensity_sum: float


class RunTimelineDTO(ApplicationDTO):
    run_id: str
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
