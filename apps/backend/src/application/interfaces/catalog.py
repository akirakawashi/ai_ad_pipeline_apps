from __future__ import annotations

from typing import Protocol

from application.common.dto import (
    CityDetailDTO,
    CityDTO,
    PipelineRunDTO,
    RouteDTO,
    RouteMeasurementDTO,
)


class CatalogRepository(Protocol):
    def list_cities(self) -> list[CityDTO]: ...

    def get_city(self, city_slug: str) -> CityDetailDTO | None: ...

    def get_route(
        self,
        city_slug: str,
        route_slug: str,
    ) -> RouteDTO | None: ...

    def list_measurements(
        self,
        *,
        city_slug: str,
        route_slug: str,
        page: int,
        page_size: int,
    ) -> tuple[list[RouteMeasurementDTO], int]: ...

    def create_measurement(
        self,
        *,
        city_slug: str,
        route_slug: str,
    ) -> RouteMeasurementDTO | None:
        """Аллоцирует sequence_number под блокировкой строки маршрута.

        Возвращает None, если города или маршрута нет.
        """
        ...

    def get_measurement(self, measurement_id: str) -> RouteMeasurementDTO | None: ...

    def list_measurement_runs(self, measurement_id: str) -> list[PipelineRunDTO]: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
