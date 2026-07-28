from __future__ import annotations

from datetime import datetime
from typing import Protocol

from application.common.dto import (
    CityDetailDTO,
    CityDTO,
    GeometryDTO,
    GeozoneDTO,
    PipelineRunDTO,
    RouteDTO,
    AssignmentDTO,
)
from domain.catalog import CityBounds


class CatalogRepository(Protocol):
    def list_cities(self, *, include_inactive: bool = False) -> list[CityDTO]: ...

    def get_city(
        self,
        city_slug: str,
        *,
        include_inactive: bool = False,
    ) -> CityDetailDTO | None: ...

    def get_route(
        self,
        city_slug: str,
        route_slug: str,
        *,
        include_inactive: bool = False,
    ) -> RouteDTO | None: ...

    # --- справочники: правка ------------------------------------------------

    def city_slug_taken(self, slug: str) -> bool: ...

    def create_city(
        self,
        *,
        slug: str,
        name: str,
        region: str | None,
        display_order: int,
    ) -> CityDTO: ...

    def update_city(self, city_slug: str, *, fields: dict[str, object]) -> bool:
        """False — города нет."""
        ...

    def route_slug_taken(self, city_slug: str, slug: str) -> bool: ...

    def create_route(
        self,
        *,
        city_slug: str,
        slug: str,
        name: str,
        color_label: str | None,
        color_hex: str | None,
        description: str | None,
        display_order: int,
    ) -> RouteDTO | None:
        """None — города нет."""
        ...

    def update_route(
        self,
        city_slug: str,
        route_slug: str,
        *,
        fields: dict[str, object],
    ) -> bool: ...

    # --- справочники: геометрия ---------------------------------------------

    def set_roads_geometry(
        self,
        city_slug: str,
        *,
        geometry: dict,
        bounds: CityBounds | None,
    ) -> bool:
        """Заливает дорожный слой и переписывает рамку города одной операцией."""
        ...

    def get_roads_geometry(self, city_slug: str) -> GeometryDTO | None: ...

    def set_route_geometry(
        self,
        city_slug: str,
        route_slug: str,
        *,
        geometry: dict,
    ) -> bool: ...

    def get_route_geometry(
        self,
        city_slug: str,
        route_slug: str,
    ) -> GeometryDTO | None: ...

    def list_assignments(
        self,
        *,
        city_slug: str,
        route_slug: str,
        page: int,
        page_size: int,
    ) -> tuple[list[AssignmentDTO], int]: ...

    def create_assignment(
        self,
        *,
        city_slug: str,
        route_slug: str,
        title: str | None,
        description: str | None,
        planned_start_at: datetime | None,
        planned_end_at: datetime | None,
        author_user_id: str | None,
    ) -> AssignmentDTO | None:
        """Аллоцирует sequence_number под блокировкой строки маршрута.

        Возвращает None, если города или маршрута нет.
        """
        ...

    def update_assignment(
        self,
        assignment_id: str,
        *,
        fields: dict[str, object],
    ) -> AssignmentDTO | None:
        """Перезаписывает только переданные поля. None — задания нет."""
        ...

    def get_assignment(self, assignment_id: str) -> AssignmentDTO | None: ...

    def list_assignment_runs(self, assignment_id: str) -> list[PipelineRunDTO]: ...

    def list_route_runs(
        self,
        city_slug: str,
        route_slug: str,
    ) -> list[PipelineRunDTO] | None:
        """Съёмки всех заданий маршрута с загруженным заданием. None — маршрута
        нет. Порядок — по времени съёмки."""
        ...

    def list_geozones(
        self,
        city_slug: str,
        route_slug: str,
    ) -> list[GeozoneDTO] | None:
        """Участки маршрута. None — маршрута нет."""
        ...

    def create_geozone(
        self,
        *,
        city_slug: str,
        route_slug: str,
        name: str,
        description: str,
        start_fraction: float,
        end_fraction: float,
        coefficient: float,
    ) -> GeozoneDTO | None:
        """None — маршрута нет; GeozoneOverlapError при пересечении."""
        ...

    def get_geozone(self, geozone_id: str) -> GeozoneDTO | None: ...

    def update_geozone(
        self,
        geozone_id: str,
        *,
        fields: dict[str, object],
    ) -> GeozoneDTO | None:
        """Перезаписывает переданные поля. None — участка нет."""
        ...

    def delete_geozone(self, geozone_id: str) -> bool:
        """False — участка нет."""
        ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
