from __future__ import annotations

from datetime import datetime

from application.common.dto import (
    CityDetailDTO,
    CityDTO,
    GeozoneDTO,
    ShootingMetricsDTO,
    AssignmentSummaryDTO,
    PaginatedAssignmentsDTO,
    ShootingBrandDTO,
    PipelineRunDTO,
    AssignmentDTO,
)
from application.exceptions import (
    CatalogNotFoundError,
    InvalidAssignmentError,
    InvalidGeozoneError,
)
from application.interfaces import CatalogRepository
from application.services.assignment_rollup import rollup_brands, rollup_totals
from application.services.pipeline_run_service import PipelineRunService
from domain.entities import PipelineRunStatus


def _check_planned_window(start: object, end: object) -> None:
    """Плановое окно не может кончиться раньше, чем началось.

    Обе границы необязательны — постановщик может знать только одну.
    """
    if isinstance(start, datetime) and isinstance(end, datetime) and end < start:
        raise InvalidAssignmentError(
            "Окончание задания не может быть раньше его начала."
        )


def _check_geozone_bounds(start: object, end: object) -> None:
    """Границы участка: 0 ≤ начало < конец ≤ 1.

    Каждое поле по отдельности держит Pydantic (ge/le), здесь — их порядок и
    полнота, в том числе при PATCH одной границы поверх лежащей в базе другой.
    """
    if not (isinstance(start, (int, float)) and isinstance(end, (int, float))):
        raise InvalidGeozoneError("Границы участка не заданы.")
    if not (0.0 <= start < end <= 1.0):
        raise InvalidGeozoneError(
            "Начало участка должно быть строго раньше конца, обе в пределах 0…1."
        )


class CatalogService:
    def __init__(
        self,
        repository: CatalogRepository,
        run_service: PipelineRunService | None = None,
    ) -> None:
        self._repository = repository
        self._run_service = run_service

    def list_cities(self) -> list[CityDTO]:
        return self._repository.list_cities()

    def get_city(self, city_slug: str) -> CityDetailDTO:
        city = self._repository.get_city(city_slug)
        if city is None:
            raise CatalogNotFoundError("Город не найден.")
        return city

    def list_assignments(
        self,
        *,
        city_slug: str,
        route_slug: str,
        page: int,
        page_size: int,
    ) -> PaginatedAssignmentsDTO:
        if self._repository.get_route(city_slug, route_slug) is None:
            raise CatalogNotFoundError("Маршрут не найден.")
        items, total = self._repository.list_assignments(
            city_slug=city_slug,
            route_slug=route_slug,
            page=page,
            page_size=page_size,
        )
        return PaginatedAssignmentsDTO(
            items=items,
            page=page,
            page_size=page_size,
            total=total,
        )

    def create_assignment(
        self,
        *,
        city_slug: str,
        route_slug: str,
        title: str | None = None,
        description: str | None = None,
        planned_start_at: datetime | None = None,
        planned_end_at: datetime | None = None,
        author_user_id: str | None = None,
    ) -> AssignmentDTO:
        _check_planned_window(planned_start_at, planned_end_at)
        assignment = self._repository.create_assignment(
            city_slug=city_slug,
            route_slug=route_slug,
            title=title,
            description=description,
            planned_start_at=planned_start_at,
            planned_end_at=planned_end_at,
            author_user_id=author_user_id,
        )
        if assignment is None:
            self._repository.rollback()
            raise CatalogNotFoundError("Маршрут не найден.")
        self._repository.commit()
        return assignment

    def update_assignment(
        self,
        assignment_id: str,
        *,
        fields: dict[str, object],
    ) -> AssignmentDTO:
        """fields содержит только те ключи, которые клиент реально прислал."""
        current = self._repository.get_assignment(assignment_id)
        if current is None:
            raise CatalogNotFoundError("Задание не найдено.")

        # Проверяем окно целиком: клиент мог прислать одну границу, и она
        # должна быть согласована с той, что уже лежит в базе.
        _check_planned_window(
            fields.get("planned_start_at", current.planned_start_at),
            fields.get("planned_end_at", current.planned_end_at),
        )

        assignment = self._repository.update_assignment(assignment_id, fields=fields)
        if assignment is None:
            self._repository.rollback()
            raise CatalogNotFoundError("Задание не найдено.")
        self._repository.commit()
        return assignment

    def get_assignment(self, assignment_id: str) -> AssignmentDTO:
        assignment = self._repository.get_assignment(assignment_id)
        if assignment is None:
            raise CatalogNotFoundError("Задание не найдено.")
        return assignment

    def list_assignment_runs(self, assignment_id: str) -> list[PipelineRunDTO]:
        if self._repository.get_assignment(assignment_id) is None:
            raise CatalogNotFoundError("Задание не найдено.")
        return self._repository.list_assignment_runs(assignment_id)

    # --- геозоны ------------------------------------------------------------

    def list_geozones(self, *, city_slug: str, route_slug: str) -> list[GeozoneDTO]:
        geozones = self._repository.list_geozones(city_slug, route_slug)
        if geozones is None:
            raise CatalogNotFoundError("Маршрут не найден.")
        return geozones

    def create_geozone(
        self,
        *,
        city_slug: str,
        route_slug: str,
        name: str,
        start_fraction: float,
        end_fraction: float,
        coefficient: float,
    ) -> GeozoneDTO:
        _check_geozone_bounds(start_fraction, end_fraction)
        geozone = self._repository.create_geozone(
            city_slug=city_slug,
            route_slug=route_slug,
            name=name,
            start_fraction=start_fraction,
            end_fraction=end_fraction,
            coefficient=coefficient,
        )
        if geozone is None:
            self._repository.rollback()
            raise CatalogNotFoundError("Маршрут не найден.")
        self._repository.commit()
        return geozone

    def get_geozone(self, geozone_id: str) -> GeozoneDTO:
        geozone = self._repository.get_geozone(geozone_id)
        if geozone is None:
            raise CatalogNotFoundError("Участок не найден.")
        return geozone

    def update_geozone(
        self,
        geozone_id: str,
        *,
        fields: dict[str, object],
    ) -> GeozoneDTO:
        """fields содержит только присланные ключи; None ни в одном не бывает —
        все поля участка обязательны, очистка запрещена."""
        current = self._repository.get_geozone(geozone_id)
        if current is None:
            raise CatalogNotFoundError("Участок не найден.")
        if any(value is None for value in fields.values()):
            raise InvalidGeozoneError("Поле участка нельзя очистить.")

        # Проверяем границы целиком: клиент мог прислать одну, вторая — из базы.
        _check_geozone_bounds(
            fields.get("start_fraction", current.start_fraction),
            fields.get("end_fraction", current.end_fraction),
        )
        geozone = self._repository.update_geozone(geozone_id, fields=fields)
        if geozone is None:
            self._repository.rollback()
            raise CatalogNotFoundError("Участок не найден.")
        self._repository.commit()
        return geozone

    def delete_geozone(self, geozone_id: str) -> None:
        if not self._repository.delete_geozone(geozone_id):
            self._repository.rollback()
            raise CatalogNotFoundError("Участок не найден.")
        self._repository.commit()

    def get_assignment_summary(self, assignment_id: str) -> AssignmentSummaryDTO:
        """Метрики задания на лету — кэш-таблицы нет, рассинхрона тоже.

        Считаем только по обработанным съёмкам: задание отдаёт цифры по мере
        готовности, а не по принципу «всё или ничего».

        Суммы тут нет намеренно. Объекты в разных съёмках — это разные
        object_id, даже если щит один и тот же физически; сложить их значит
        посчитать один щит столько раз, сколько раз проехали. Меряем
        «сколько видно за съёмку», поэтому усредняем (see assignment_rollup).
        """
        assignment = self._repository.get_assignment(assignment_id)
        if assignment is None:
            raise CatalogNotFoundError("Задание не найдено.")
        if self._run_service is None:
            raise RuntimeError("CatalogService создан без run_service.")

        runs = self._repository.list_assignment_runs(assignment_id)
        shootings = [
            self._build_shooting(run)
            for run in runs
            if run.status == PipelineRunStatus.COMPLETED
        ]

        return AssignmentSummaryDTO(
            assignment=assignment,
            totals=rollup_totals(shootings, shootings_total=len(runs)),
            brands=rollup_brands(shootings),
            shootings=shootings,
        )

    def _build_shooting(self, run: PipelineRunDTO) -> ShootingMetricsDTO:
        summary = self._run_service.get_summary(run.run_id)
        return ShootingMetricsDTO(
            run_id=run.run_id,
            source_name=run.source_name,
            duration_sec=run.duration_sec or 0.0,
            objects_count=summary.totals.total_objects,
            visibility_index=summary.totals.visibility_index,
            brands=[
                ShootingBrandDTO(
                    brand=brand.brand,
                    objects_count=brand.object_count or 0,
                    visibility_index=brand.sum_visibility_value or 0.0,
                )
                for brand in summary.brands
            ],
        )
