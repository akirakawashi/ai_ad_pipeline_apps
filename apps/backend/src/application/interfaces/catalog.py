from __future__ import annotations

from datetime import datetime
from typing import Protocol

from application.common.dto import (
    CityDetailDTO,
    CityDTO,
    PipelineRunDTO,
    RouteDTO,
    AssignmentDTO,
)


class CatalogRepository(Protocol):
    def list_cities(self) -> list[CityDTO]: ...

    def get_city(self, city_slug: str) -> CityDetailDTO | None: ...

    def get_route(
        self,
        city_slug: str,
        route_slug: str,
    ) -> RouteDTO | None: ...

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

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
