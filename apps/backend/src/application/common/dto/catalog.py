from __future__ import annotations

from datetime import datetime

from pydantic import Field

from application.common.dto.base import ApplicationDTO
from application.common.dto.pipeline import CityRefDTO, RouteRefDTO
from application.common.dto.users import UserDTO


class RouteDTO(ApplicationDTO):
    id: str
    slug: str
    name: str
    color_label: str | None
    color_hex: str | None
    description: str | None = None
    geojson_path: str
    display_order: int
    assignment_count: int = 0
    video_count: int = 0


class CityDTO(ApplicationDTO):
    id: str
    slug: str
    name: str
    region: str | None
    roads_geojson_path: str | None
    display_order: int
    route_count: int = 0
    assignment_count: int = 0
    video_count: int = 0


class CityDetailDTO(CityDTO):
    routes: list[RouteDTO] = Field(default_factory=list)


class AssignmentStatusCountsDTO(ApplicationDTO):
    uploading: int = 0
    upload_failed: int = 0
    queued: int = 0
    processing: int = 0
    completed: int = 0
    processing_failed: int = 0


class AssignmentDTO(ApplicationDTO):
    id: str
    sequence_number: int
    title: str
    description: str | None = None
    route: RouteRefDTO
    city: CityRefDTO
    # Постановщик задания.
    author: UserDTO | None = None
    # Плановое окно задаёт постановщик.
    planned_start_at: datetime | None = None
    planned_end_at: datetime | None = None
    # Фактическое окно не хранится: выводится из времён съёмок задания.
    # None — ни у одной съёмки не заполнено время съёмки.
    actual_start_at: datetime | None = None
    actual_end_at: datetime | None = None
    video_count: int = 0
    status_counts: AssignmentStatusCountsDTO = Field(
        default_factory=AssignmentStatusCountsDTO
    )
    created_at: datetime | None = None


class PaginatedAssignmentsDTO(ApplicationDTO):
    items: list[AssignmentDTO]
    page: int
    page_size: int
    total: int


class ShootingBrandDTO(ApplicationDTO):
    """Итог одного бренда в одной съёмке."""

    brand: str
    objects_count: int = 0
    visibility_index: float = 0.0


class ShootingMetricsDTO(ApplicationDTO):
    """Сырые метрики одной съёмки — вход для любой свёртки.

    Этот слой не зависит от того, как бизнес решит считать задание:
    среднее, медиана, с отбраковкой коротких съёмок или без.
    """

    run_id: str
    source_name: str
    duration_sec: float = 0.0
    objects_count: int = 0
    visibility_index: float = 0.0
    brands: list[ShootingBrandDTO] = Field(default_factory=list)


class AssignmentStatDTO(ApplicationDTO):
    """Величина «на съёмку»: среднее и разброс между съёмками."""

    mean: float = 0.0
    std: float = 0.0


class AssignmentBrandDTO(ApplicationDTO):
    brand: str
    objects_per_shooting: AssignmentStatDTO = Field(default_factory=AssignmentStatDTO)
    visibility_per_shooting: AssignmentStatDTO = Field(
        default_factory=AssignmentStatDTO
    )
    # Доля от суммы средних по заданию.
    visibility_share: float = 0.0


class AssignmentTotalsDTO(ApplicationDTO):
    shootings_total: int = 0
    shootings_completed: int = 0
    # Единственная величина, которую суммируем: это «сколько наснимали».
    duration_sec: float = 0.0
    objects_per_shooting: AssignmentStatDTO = Field(default_factory=AssignmentStatDTO)
    visibility_per_shooting: AssignmentStatDTO = Field(
        default_factory=AssignmentStatDTO
    )


class AssignmentSummaryDTO(ApplicationDTO):
    assignment: AssignmentDTO
    totals: AssignmentTotalsDTO
    brands: list[AssignmentBrandDTO] = Field(default_factory=list)
    shootings: list[ShootingMetricsDTO] = Field(default_factory=list)
