from __future__ import annotations

from datetime import datetime

from pydantic import Field

from application.common.dto.pipeline import (
    ApplicationDTO,
    BrandSummaryDTO,
    CityRefDTO,
    RouteRefDTO,
)


class RouteDTO(ApplicationDTO):
    id: str
    slug: str
    name: str
    color_label: str | None
    color_hex: str | None
    geojson_path: str
    display_order: int
    measurement_count: int = 0
    video_count: int = 0


class CityDTO(ApplicationDTO):
    id: str
    slug: str
    name: str
    region: str | None
    roads_geojson_path: str | None
    display_order: int
    route_count: int = 0
    measurement_count: int = 0
    video_count: int = 0


class CityDetailDTO(CityDTO):
    routes: list[RouteDTO] = Field(default_factory=list)


class MeasurementStatusCountsDTO(ApplicationDTO):
    uploading: int = 0
    upload_failed: int = 0
    queued: int = 0
    processing: int = 0
    completed: int = 0
    processing_failed: int = 0


class RouteMeasurementDTO(ApplicationDTO):
    id: str
    sequence_number: int
    title: str
    route: RouteRefDTO
    city: CityRefDTO
    video_count: int = 0
    status_counts: MeasurementStatusCountsDTO = Field(
        default_factory=MeasurementStatusCountsDTO
    )
    created_at: datetime | None = None


class PaginatedMeasurementsDTO(ApplicationDTO):
    items: list[RouteMeasurementDTO]
    page: int
    page_size: int
    total: int


class MeasurementTotalsDTO(ApplicationDTO):
    total_objects: int = 0
    # Среднее по проездам, взвешенное по длительности: короткий проезд
    # не должен весить столько же, сколько десятиминутный.
    visibility_index: float = 0.0
    video_count: int = 0
    completed_count: int = 0
    duration_sec: float = 0.0


class MeasurementSummaryDTO(ApplicationDTO):
    measurement: RouteMeasurementDTO
    totals: MeasurementTotalsDTO
    brands: list[BrandSummaryDTO] = Field(default_factory=list)
