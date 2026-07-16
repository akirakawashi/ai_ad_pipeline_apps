from __future__ import annotations

from collections import defaultdict

from application.common.dto import (
    BrandSummaryDTO,
    CityDetailDTO,
    CityDTO,
    MeasurementSummaryDTO,
    MeasurementTotalsDTO,
    PaginatedMeasurementsDTO,
    PipelineRunDTO,
    RouteMeasurementDTO,
)
from application.exceptions import CatalogNotFoundError
from application.interfaces import CatalogRepository
from application.services.pipeline_run_service import PipelineRunService
from domain.entities import PipelineRunStatus


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

    def list_measurements(
        self,
        *,
        city_slug: str,
        route_slug: str,
        page: int,
        page_size: int,
    ) -> PaginatedMeasurementsDTO:
        if self._repository.get_route(city_slug, route_slug) is None:
            raise CatalogNotFoundError("Маршрут не найден.")
        items, total = self._repository.list_measurements(
            city_slug=city_slug,
            route_slug=route_slug,
            page=page,
            page_size=page_size,
        )
        return PaginatedMeasurementsDTO(
            items=items,
            page=page,
            page_size=page_size,
            total=total,
        )

    def create_measurement(self, *, city_slug: str, route_slug: str) -> RouteMeasurementDTO:
        measurement = self._repository.create_measurement(
            city_slug=city_slug,
            route_slug=route_slug,
        )
        if measurement is None:
            self._repository.rollback()
            raise CatalogNotFoundError("Маршрут не найден.")
        self._repository.commit()
        return measurement

    def get_measurement(self, measurement_id: str) -> RouteMeasurementDTO:
        measurement = self._repository.get_measurement(measurement_id)
        if measurement is None:
            raise CatalogNotFoundError("Замер не найден.")
        return measurement

    def list_measurement_runs(self, measurement_id: str) -> list[PipelineRunDTO]:
        if self._repository.get_measurement(measurement_id) is None:
            raise CatalogNotFoundError("Замер не найден.")
        return self._repository.list_measurement_runs(measurement_id)

    def get_measurement_summary(self, measurement_id: str) -> MeasurementSummaryDTO:
        """Агрегат по замеру на лету — кэш-таблицы нет, рассинхрона тоже.

        Считаем только по обработанным видео: замер отдаёт метрики по мере
        готовности, а не по принципу «всё или ничего».
        """
        measurement = self._repository.get_measurement(measurement_id)
        if measurement is None:
            raise CatalogNotFoundError("Замер не найден.")
        if self._run_service is None:
            raise RuntimeError("CatalogService создан без run_service.")

        runs = self._repository.list_measurement_runs(measurement_id)
        completed = [
            run for run in runs if run.status == PipelineRunStatus.COMPLETED
        ]

        merged: dict[str, BrandSummaryDTO] = {}
        totals = MeasurementTotalsDTO(
            video_count=len(runs),
            completed_count=len(completed),
        )
        weighted: dict[str, float] = defaultdict(float)

        for run in completed:
            summary = self._run_service.get_summary(run.run_id)
            totals.total_objects += summary.totals.total_objects
            totals.visibility_index += summary.totals.visibility_index
            totals.duration_sec += run.duration_sec or 0.0
            for brand in summary.brands:
                key = brand.brand
                if key in merged:
                    merged[key].object_count += brand.object_count
                else:
                    merged[key] = brand.model_copy(deep=True)
                weighted[key] += brand.video_visibility_weighted_seconds or 0.0

        for key, value in weighted.items():
            merged[key].video_visibility_weighted_seconds = value

        brands = sorted(
            merged.values(),
            key=lambda item: item.object_count,
            reverse=True,
        )
        return MeasurementSummaryDTO(measurement=measurement, totals=totals, brands=brands)
