from __future__ import annotations

from datetime import datetime

from pydantic import Field

from application.common.dto.base import ApplicationDTO
from application.common.dto.pipeline import (
    CityRefDTO,
    RouteRefDTO,
    RunAssignmentRefDTO,
)
from application.common.dto.users import UserDTO
from domain.catalog import CatalogImportStatus


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


class GeozoneDTO(ApplicationDTO):
    """Участок маршрута со значимостью β: доля [start, end) от длительности.

    Границы локальны для маршрута и применяются ко всем его съёмкам. Вне
    размеченных участков β = 1.0 — считается на бэкенде, тут его нет.
    """

    id: str
    route_id: str
    name: str
    description: str = ""
    start_fraction: float
    end_fraction: float
    coefficient: float
    created_at: datetime | None = None
    updated_at: datetime | None = None


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
    # Отображаемое имя: своё название либо запасное «Задание №N · дата».
    title: str
    # Хранимое название, None — своего нет. Форма правки обязана редактировать
    # именно его: подставь в поле ввода вычисленный title — и он молча станет
    # хранимым, зафиксировав номер и дату в тексте навсегда.
    custom_title: str | None = None
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

    Единица учёта во всей аналитике: и задание, и маршрут считаются из списка
    таких записей напрямую. Уровня «среднее из средних» нет — маршрут не
    складывается из результатов заданий, он читает те же съёмки.

    Этот слой не зависит от того, как бизнес решит считать свёртку: среднее,
    медиана, с отбраковкой коротких съёмок или без.
    """

    run_id: str
    source_name: str
    # Когда снимали, а не когда обрабатывали: ось времени в графиках маршрута.
    shot_started_at: datetime | None = None
    duration_sec: float = 0.0
    objects_count: int = 0
    visibility_index: float = 0.0
    brands: list[ShootingBrandDTO] = Field(default_factory=list)


class RouteShootingMetricsDTO(ShootingMetricsDTO):
    """То же плюс задание: на уровне маршрута его надо показать в списке.

    Внутри задания такое поле было бы шумом — там задание и так одно.
    """

    assignment: RunAssignmentRefDTO


class MetricStatDTO(ApplicationDTO):
    """Величина «на съёмку»: среднее и разброс между съёмками."""

    mean: float = 0.0
    std: float = 0.0


class RollupBrandDTO(ApplicationDTO):
    brand: str
    objects_per_shooting: MetricStatDTO = Field(default_factory=MetricStatDTO)
    visibility_per_shooting: MetricStatDTO = Field(default_factory=MetricStatDTO)
    # Доля от суммы средних по всем брендам свёртки.
    visibility_share: float = 0.0


class RollupTotalsDTO(ApplicationDTO):
    shootings_total: int = 0
    shootings_completed: int = 0
    # Единственная величина, которую суммируем: это «сколько наснимали».
    duration_sec: float = 0.0
    objects_per_shooting: MetricStatDTO = Field(default_factory=MetricStatDTO)
    visibility_per_shooting: MetricStatDTO = Field(default_factory=MetricStatDTO)


class AssignmentSummaryDTO(ApplicationDTO):
    assignment: AssignmentDTO
    totals: RollupTotalsDTO
    brands: list[RollupBrandDTO] = Field(default_factory=list)
    shootings: list[ShootingMetricsDTO] = Field(default_factory=list)


class RouteSummaryDTO(ApplicationDTO):
    """Свёртка маршрута: те же функции, что у задания, но список длиннее.

    `assignments_total` — сколько заданий на маршруте вообще; съёмки в
    `shootings` идут плоским списком по времени съёмки, задания служат
    подписью, а не ступенькой усреднения.
    """

    route: RouteDTO
    assignments_total: int = 0
    totals: RollupTotalsDTO
    brands: list[RollupBrandDTO] = Field(default_factory=list)
    shootings: list[RouteShootingMetricsDTO] = Field(default_factory=list)


# --- каталог рекламных конструкций ------------------------------------------


class AdStructureDTO(ApplicationDTO):
    """Конструкция каталога: точка на карте.

    Не путать с находкой на видео: та живёт внутри одной съёмки. Здесь —
    физический щит. Названия в источнике нет, им служит адрес.
    """

    id: str
    city_id: str
    address: str
    latitude: float
    longitude: float
    # Сколько строк файла схлопнулось в эту точку: щиты стоят треугольником.
    surfaces_count: int = 1


class PaginatedAdStructuresDTO(ApplicationDTO):
    items: list[AdStructureDTO]
    page: int
    page_size: int
    total: int


class CatalogImportDTO(ApplicationDTO):
    """Ревизия каталога города. `revision` пуст, пока пак не применён."""

    id: str
    city_id: str
    revision: int | None = None
    status: CatalogImportStatus
    is_current: bool = False
    file_names: list[str] = Field(default_factory=list)
    rows_read: int = 0
    rows_rejected: int = 0
    points_total: int = 0
    files_rejected: int = 0
    uploaded_by: UserDTO | None = None
    applied_at: datetime | None = None
    created_at: datetime | None = None


class RejectedFileDTO(ApplicationDTO):
    """Файл, отклонённый целиком, и почему."""

    file_name: str
    reason: str


class RowErrorDTO(ApplicationDTO):
    """Строка, которую не взяли: где она и почему."""

    file_name: str
    row_number: int
    reason: str


class CatalogImportReportDTO(ApplicationDTO):
    """Что произойдёт, если применить пак. Показывается до подтверждения.

    Сравнение с текущей ревизией — по близости координат, поэтому «исчезло» и
    «появилось» приблизительны и годятся только для глаз. Строка «−180 точек»
    здесь важнее всех остальных: неполный файл выглядит именно так.
    """

    catalog_import: CatalogImportDTO
    points_before: int
    points_after: int
    added: int
    removed: int
    # Сколько строк схлопнулось: прочитано минус получившиеся точки.
    collapsed_rows: int
    rejected_files: list[RejectedFileDTO] = Field(default_factory=list)
    row_errors: list[RowErrorDTO] = Field(default_factory=list)
    # Файлы, где нашлись лишние листы: читаем только первый, остальное могло
    # быть черновиком — пусть человек знает.
    files_with_extra_sheets: list[str] = Field(default_factory=list)
