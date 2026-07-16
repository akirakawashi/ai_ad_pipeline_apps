from __future__ import annotations

from datetime import datetime

from pydantic import Field

from application.common.dto.pipeline import (
    ApplicationDTO,
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


class PassBrandDTO(ApplicationDTO):
    """Итог одного бренда в одном проезде."""

    brand: str
    objects_count: int = 0
    visibility_index: float = 0.0


class MeasurementPassDTO(ApplicationDTO):
    """Сырые метрики одного проезда — вход для любой свёртки.

    Этот слой не зависит от того, как бизнес решит считать замер:
    среднее, медиана, с отбраковкой коротких проездов или без.
    """

    run_id: str
    source_name: str
    duration_sec: float = 0.0
    objects_count: int = 0
    visibility_index: float = 0.0
    brands: list[PassBrandDTO] = Field(default_factory=list)


class MeasurementStatDTO(ApplicationDTO):
    """Величина «на проезд»: среднее и разброс между проездами."""

    mean: float = 0.0
    std: float = 0.0


class MeasurementBrandDTO(ApplicationDTO):
    brand: str
    objects_per_pass: MeasurementStatDTO = Field(default_factory=MeasurementStatDTO)
    visibility_per_pass: MeasurementStatDTO = Field(
        default_factory=MeasurementStatDTO
    )
    # Доля от суммы средних по замеру.
    visibility_share: float = 0.0


class MeasurementTotalsDTO(ApplicationDTO):
    passes_total: int = 0
    passes_completed: int = 0
    # Единственная величина, которую суммируем: это «сколько наснимали».
    duration_sec: float = 0.0
    objects_per_pass: MeasurementStatDTO = Field(default_factory=MeasurementStatDTO)
    visibility_per_pass: MeasurementStatDTO = Field(
        default_factory=MeasurementStatDTO
    )


class MeasurementSummaryDTO(ApplicationDTO):
    measurement: RouteMeasurementDTO
    totals: MeasurementTotalsDTO
    brands: list[MeasurementBrandDTO] = Field(default_factory=list)
    passes: list[MeasurementPassDTO] = Field(default_factory=list)
