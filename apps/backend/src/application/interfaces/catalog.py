from __future__ import annotations

from typing import Protocol

from application.common.dto import (
    CityDetailDTO,
    CityDTO,
    PipelineRunDTO,
    RouteBatchDTO,
    RouteDTO,
)


class CatalogRepository(Protocol):
    def list_cities(self) -> list[CityDTO]: ...

    def get_city(self, city_slug: str) -> CityDetailDTO | None: ...

    def get_route(
        self,
        city_slug: str,
        route_slug: str,
    ) -> RouteDTO | None: ...

    def list_batches(
        self,
        *,
        city_slug: str,
        route_slug: str,
        page: int,
        page_size: int,
    ) -> tuple[list[RouteBatchDTO], int]: ...

    def create_batch(
        self,
        *,
        city_slug: str,
        route_slug: str,
    ) -> RouteBatchDTO | None:
        """Аллоцирует sequence_number под блокировкой строки маршрута.

        Возвращает None, если города или маршрута нет.
        """
        ...

    def get_batch(self, batch_id: str) -> RouteBatchDTO | None: ...

    def list_batch_runs(self, batch_id: str) -> list[PipelineRunDTO]: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
