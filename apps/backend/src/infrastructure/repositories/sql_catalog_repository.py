from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import noload, selectinload
from sqlmodel import Session, select

from application.common.dto import (
    AssignmentDTO,
    AssignmentStatusCountsDTO,
    CityDetailDTO,
    CityDTO,
    GeozoneDTO,
    PipelineRunDTO,
    RouteDTO,
)
from application.exceptions import GeozoneOverlapError
from domain.geozones import GeozoneInterval, overlaps
from infrastructure.database.models import (
    Assignment,
    City,
    PipelineRun,
    Route,
    RouteGeozone,
)
from infrastructure.repositories.assignment_mapping import (
    assignment_title,
    city_ref,
    route_ref,
    user_ref,
)
from infrastructure.repositories.sql_pipeline_run_repository import _run_to_dto

# Фактическое окно задания: (начало первой съёмки, конец последней).
ShotWindow = tuple[datetime | None, datetime | None]


def _route_to_dto(
    route: Route,
    *,
    assignment_count: int = 0,
    video_count: int = 0,
) -> RouteDTO:
    return RouteDTO(
        id=route.routes_id,
        slug=route.slug,
        name=route.name,
        color_label=route.color_label,
        color_hex=route.color_hex,
        description=route.description,
        geojson_path=route.geojson_path,
        display_order=route.display_order,
        assignment_count=assignment_count,
        video_count=video_count,
    )


def _geozone_to_dto(geozone: RouteGeozone) -> GeozoneDTO:
    return GeozoneDTO(
        id=geozone.route_geozones_id,
        route_id=geozone.routes_id,
        name=geozone.name,
        start_fraction=geozone.start_fraction,
        end_fraction=geozone.end_fraction,
        coefficient=geozone.coefficient,
        created_at=geozone.created_at,
        updated_at=geozone.updated_at,
    )


def _assignment_to_dto(
    assignment: Assignment,
    route: Route,
    city: City,
    *,
    video_count: int = 0,
    status_counts: AssignmentStatusCountsDTO | None = None,
    shot_window: ShotWindow = (None, None),
) -> AssignmentDTO:
    actual_start_at, actual_end_at = shot_window
    return AssignmentDTO(
        id=assignment.assignments_id,
        sequence_number=assignment.sequence_number,
        title=assignment_title(assignment),
        custom_title=assignment.title,
        description=assignment.description,
        route=route_ref(route),
        city=city_ref(city),
        author=user_ref(assignment.author),
        planned_start_at=assignment.planned_start_at,
        planned_end_at=assignment.planned_end_at,
        actual_start_at=actual_start_at,
        actual_end_at=actual_end_at,
        video_count=video_count,
        status_counts=status_counts or AssignmentStatusCountsDTO(),
        created_at=assignment.created_at,
    )


class SqlCatalogRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # --- счётчики -------------------------------------------------------

    def _assignment_counts_by_route(self) -> dict[str, int]:
        rows = self._session.exec(
            select(Assignment.routes_id, func.count(Assignment.assignments_id))
            .group_by(Assignment.routes_id)
        ).all()
        return {routes_id: int(count) for routes_id, count in rows}

    def _video_counts_by_route(self) -> dict[str, int]:
        rows = self._session.exec(
            select(Assignment.routes_id, func.count(PipelineRun.pipeline_runs_id))
            .join(PipelineRun, PipelineRun.assignments_id == Assignment.assignments_id)
            .group_by(Assignment.routes_id)
        ).all()
        return {routes_id: int(count) for routes_id, count in rows}

    def _video_counts_by_assignment(self, assignment_ids: list[str]) -> dict[str, int]:
        if not assignment_ids:
            return {}
        rows = self._session.exec(
            select(PipelineRun.assignments_id, func.count(PipelineRun.pipeline_runs_id))
            .where(PipelineRun.assignments_id.in_(assignment_ids))
            .group_by(PipelineRun.assignments_id)
        ).all()
        return {assignment_id: int(count) for assignment_id, count in rows}

    def _shot_windows_by_assignment(
        self,
        assignment_ids: list[str],
    ) -> dict[str, ShotWindow]:
        """Фактическое окно каждого задания из времён его съёмок.

        Одним запросом на весь список, без N+1. Конец считаем в Python как
        начало + длительность: интервальная арифметика в SQL привязала бы
        репозиторий к диалекту ради экономии, которой на ≤20 съёмках нет.
        """
        if not assignment_ids:
            return {}
        rows = self._session.exec(
            select(
                PipelineRun.assignments_id,
                PipelineRun.shot_started_at,
                PipelineRun.duration_sec,
            ).where(
                PipelineRun.assignments_id.in_(assignment_ids),
                PipelineRun.shot_started_at.is_not(None),
            )
        ).all()

        result: dict[str, ShotWindow] = {}
        for assignment_id, shot_started_at, duration_sec in rows:
            start, end = result.get(assignment_id, (None, None))
            finish = shot_started_at + timedelta(seconds=duration_sec or 0.0)
            result[assignment_id] = (
                shot_started_at if start is None else min(start, shot_started_at),
                finish if end is None else max(end, finish),
            )
        return result

    def _status_counts_by_assignment(
        self,
        assignment_ids: list[str],
    ) -> dict[str, AssignmentStatusCountsDTO]:
        if not assignment_ids:
            return {}
        rows = self._session.exec(
            select(
                PipelineRun.assignments_id,
                PipelineRun.status,
                func.count(PipelineRun.pipeline_runs_id),
            )
            .where(PipelineRun.assignments_id.in_(assignment_ids))
            .group_by(PipelineRun.assignments_id, PipelineRun.status)
        ).all()
        result: dict[str, AssignmentStatusCountsDTO] = {}
        for assignment_id, status, count in rows:
            counts = result.setdefault(assignment_id, AssignmentStatusCountsDTO())
            if hasattr(counts, status):
                setattr(counts, status, int(count))
        return result

    # --- города и маршруты ----------------------------------------------

    def list_cities(self) -> list[CityDTO]:
        cities = self._session.exec(
            select(City)
            .where(City.is_active.is_(True))
            .options(noload(City.routes))
            .order_by(City.display_order, City.name)
        ).all()

        route_rows = self._session.exec(
            select(Route.cities_id, func.count(Route.routes_id))
            .where(Route.is_active.is_(True))
            .group_by(Route.cities_id)
        ).all()
        route_counts = {cities_id: int(count) for cities_id, count in route_rows}

        assignment_rows = self._session.exec(
            select(Route.cities_id, func.count(Assignment.assignments_id))
            .join(Assignment, Assignment.routes_id == Route.routes_id)
            .group_by(Route.cities_id)
        ).all()
        assignment_counts = {cities_id: int(count) for cities_id, count in assignment_rows}

        video_rows = self._session.exec(
            select(Route.cities_id, func.count(PipelineRun.pipeline_runs_id))
            .join(Assignment, Assignment.routes_id == Route.routes_id)
            .join(
                PipelineRun,
                PipelineRun.assignments_id == Assignment.assignments_id,
            )
            .group_by(Route.cities_id)
        ).all()
        video_counts = {cities_id: int(count) for cities_id, count in video_rows}

        return [
            CityDTO(
                id=city.cities_id,
                slug=city.slug,
                name=city.name,
                region=city.region,
                roads_geojson_path=city.roads_geojson_path,
                display_order=city.display_order,
                route_count=route_counts.get(city.cities_id, 0),
                assignment_count=assignment_counts.get(city.cities_id, 0),
                video_count=video_counts.get(city.cities_id, 0),
            )
            for city in cities
        ]

    def get_city(self, city_slug: str) -> CityDetailDTO | None:
        city = self._session.exec(
            select(City)
            .where(City.slug == city_slug)
            .options(selectinload(City.routes))
        ).first()
        if city is None:
            return None

        assignment_counts = self._assignment_counts_by_route()
        video_counts = self._video_counts_by_route()
        routes = [route for route in city.routes if route.is_active]

        return CityDetailDTO(
            id=city.cities_id,
            slug=city.slug,
            name=city.name,
            region=city.region,
            roads_geojson_path=city.roads_geojson_path,
            display_order=city.display_order,
            route_count=len(routes),
            assignment_count=sum(assignment_counts.get(r.routes_id, 0) for r in routes),
            video_count=sum(video_counts.get(r.routes_id, 0) for r in routes),
            routes=[
                _route_to_dto(
                    route,
                    assignment_count=assignment_counts.get(route.routes_id, 0),
                    video_count=video_counts.get(route.routes_id, 0),
                )
                for route in routes
            ],
        )

    def _get_route_model(self, city_slug: str, route_slug: str) -> Route | None:
        return self._session.exec(
            select(Route)
            .join(City, City.cities_id == Route.cities_id)
            .where(City.slug == city_slug, Route.slug == route_slug)
        ).first()

    def get_route(self, city_slug: str, route_slug: str) -> RouteDTO | None:
        route = self._get_route_model(city_slug, route_slug)
        if route is None:
            return None
        return _route_to_dto(
            route,
            assignment_count=self._assignment_counts_by_route().get(route.routes_id, 0),
            video_count=self._video_counts_by_route().get(route.routes_id, 0),
        )

    # --- задания ------------------------------------------------------------

    def list_assignments(
        self,
        *,
        city_slug: str,
        route_slug: str,
        page: int,
        page_size: int,
    ) -> tuple[list[AssignmentDTO], int]:
        route = self._get_route_model(city_slug, route_slug)
        if route is None:
            return [], 0
        city = route.city
        if city is None:
            return [], 0

        total = self._session.exec(
            select(func.count(Assignment.assignments_id)).where(
                Assignment.routes_id == route.routes_id
            )
        ).one()

        assignments = self._session.exec(
            select(Assignment)
            .where(Assignment.routes_id == route.routes_id)
            .options(selectinload(Assignment.author))
            .order_by(Assignment.sequence_number.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()

        assignment_ids = [assignment.assignments_id for assignment in assignments]
        video_counts = self._video_counts_by_assignment(assignment_ids)
        status_counts = self._status_counts_by_assignment(assignment_ids)
        shot_windows = self._shot_windows_by_assignment(assignment_ids)

        return [
            _assignment_to_dto(
                assignment,
                route,
                city,
                video_count=video_counts.get(assignment.assignments_id, 0),
                status_counts=status_counts.get(assignment.assignments_id),
                shot_window=shot_windows.get(assignment.assignments_id, (None, None)),
            )
            for assignment in assignments
        ], int(total)

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
        route = self._get_route_model(city_slug, route_slug)
        if route is None:
            return None

        # Блокируем строку маршрута: два одновременных POST сериализуются здесь
        # и получают разные номера. uq_assignments_route_sequence — подстраховка.
        self._session.exec(
            select(Route)
            .where(Route.routes_id == route.routes_id)
            .with_for_update()
        ).first()

        next_sequence = self._session.exec(
            select(
                func.coalesce(func.max(Assignment.sequence_number), 0) + 1
            ).where(Assignment.routes_id == route.routes_id)
        ).one()

        assignment = Assignment(
            routes_id=route.routes_id,
            sequence_number=int(next_sequence),
            title=title,
            description=description,
            planned_start_at=planned_start_at,
            planned_end_at=planned_end_at,
            author_users_id=author_user_id,
        )
        self._session.add(assignment)
        self._session.flush()
        self._session.refresh(assignment)

        city = route.city
        if city is None:
            return None
        return _assignment_to_dto(assignment, route, city)

    def update_assignment(
        self,
        assignment_id: str,
        *,
        fields: dict[str, object],
    ) -> AssignmentDTO | None:
        """Перезаписывает только переданные ключи: PATCH, а не PUT."""
        assignment = self._get_assignment_model(assignment_id)
        if assignment is None or assignment.route is None or assignment.route.city is None:
            return None
        for name, value in fields.items():
            setattr(assignment, name, value)
        self._session.add(assignment)
        self._session.flush()
        self._session.refresh(assignment)
        return self._assignment_dto(assignment)

    def _get_assignment_model(self, assignment_id: str) -> Assignment | None:
        return self._session.exec(
            select(Assignment)
            .where(Assignment.assignments_id == assignment_id)
            .options(
                selectinload(Assignment.route).selectinload(Route.city),
                selectinload(Assignment.author),
            )
        ).first()

    def _assignment_dto(self, assignment: Assignment) -> AssignmentDTO:
        assignment_id = assignment.assignments_id
        return _assignment_to_dto(
            assignment,
            assignment.route,
            assignment.route.city,
            video_count=self._video_counts_by_assignment([assignment_id]).get(assignment_id, 0),
            status_counts=self._status_counts_by_assignment([assignment_id]).get(assignment_id),
            shot_window=self._shot_windows_by_assignment([assignment_id]).get(
                assignment_id, (None, None)
            ),
        )

    def get_assignment(self, assignment_id: str) -> AssignmentDTO | None:
        assignment = self._get_assignment_model(assignment_id)
        if assignment is None or assignment.route is None or assignment.route.city is None:
            return None
        return self._assignment_dto(assignment)

    def list_assignment_runs(self, assignment_id: str) -> list[PipelineRunDTO]:
        runs = self._session.exec(
            select(PipelineRun)
            .where(PipelineRun.assignments_id == assignment_id)
            .options(
                selectinload(PipelineRun.artifacts),
                noload(PipelineRun.events),
                noload(PipelineRun.assignment),
            )
            .order_by(PipelineRun.created_at)
        ).all()
        return [_run_to_dto(run) for run in runs]

    def lock_assignment(self, assignment_id: str) -> bool:
        """Блокирует строку задания. False, если задания нет."""
        assignment = self._session.exec(
            select(Assignment)
            .where(Assignment.assignments_id == assignment_id)
            .with_for_update()
        ).first()
        return assignment is not None

    def count_assignment_runs(self, assignment_id: str) -> int:
        total = self._session.exec(
            select(func.count(PipelineRun.pipeline_runs_id)).where(
                PipelineRun.assignments_id == assignment_id
            )
        ).one()
        return int(total)

    # --- геозоны ------------------------------------------------------------

    def list_geozones(
        self,
        city_slug: str,
        route_slug: str,
    ) -> list[GeozoneDTO] | None:
        """Участки маршрута по возрастанию начала. None — маршрута нет."""
        route = self._get_route_model(city_slug, route_slug)
        if route is None:
            return None
        rows = self._session.exec(
            select(RouteGeozone)
            .where(RouteGeozone.routes_id == route.routes_id)
            .order_by(RouteGeozone.start_fraction)
        ).all()
        return [_geozone_to_dto(geozone) for geozone in rows]

    def create_geozone(
        self,
        *,
        city_slug: str,
        route_slug: str,
        name: str,
        start_fraction: float,
        end_fraction: float,
        coefficient: float,
    ) -> GeozoneDTO | None:
        """Добавляет участок. None — маршрута нет; пересечение → исключение."""
        route = self._get_route_model(city_slug, route_slug)
        if route is None:
            return None

        # Блокируем строку маршрута: под замком читаем соседей и проверяем
        # пересечение, чтобы два одновременных POST не вставили налезающие
        # участки — БД такой инвариант через constraint не выразить.
        self._lock_route(route.routes_id)
        self._ensure_no_overlap(route.routes_id, start_fraction, end_fraction)

        geozone = RouteGeozone(
            routes_id=route.routes_id,
            name=name,
            start_fraction=start_fraction,
            end_fraction=end_fraction,
            coefficient=coefficient,
        )
        self._session.add(geozone)
        self._session.flush()
        self._session.refresh(geozone)
        return _geozone_to_dto(geozone)

    def get_geozone(self, geozone_id: str) -> GeozoneDTO | None:
        geozone = self._get_geozone_model(geozone_id)
        return _geozone_to_dto(geozone) if geozone is not None else None

    def update_geozone(
        self,
        geozone_id: str,
        *,
        fields: dict[str, object],
    ) -> GeozoneDTO | None:
        """Перезаписывает переданные поля. None — участка нет; пересечение →
        исключение. Слитые границы проверяются до записи, без грязной модели."""
        geozone = self._get_geozone_model(geozone_id)
        if geozone is None:
            return None

        self._lock_route(geozone.routes_id)
        merged_start = fields.get("start_fraction", geozone.start_fraction)
        merged_end = fields.get("end_fraction", geozone.end_fraction)
        self._ensure_no_overlap(
            geozone.routes_id,
            float(merged_start),
            float(merged_end),
            exclude_id=geozone.route_geozones_id,
        )

        for name, value in fields.items():
            setattr(geozone, name, value)
        self._session.add(geozone)
        self._session.flush()
        self._session.refresh(geozone)
        return _geozone_to_dto(geozone)

    def delete_geozone(self, geozone_id: str) -> bool:
        """False, если участка нет."""
        geozone = self._get_geozone_model(geozone_id)
        if geozone is None:
            return False
        self._session.delete(geozone)
        self._session.flush()
        return True

    def _get_geozone_model(self, geozone_id: str) -> RouteGeozone | None:
        return self._session.exec(
            select(RouteGeozone).where(
                RouteGeozone.route_geozones_id == geozone_id
            )
        ).first()

    def _lock_route(self, routes_id: str) -> None:
        self._session.exec(
            select(Route).where(Route.routes_id == routes_id).with_for_update()
        ).first()

    def _ensure_no_overlap(
        self,
        routes_id: str,
        start_fraction: float,
        end_fraction: float,
        *,
        exclude_id: str | None = None,
    ) -> None:
        query = select(RouteGeozone).where(RouteGeozone.routes_id == routes_id)
        if exclude_id is not None:
            query = query.where(RouteGeozone.route_geozones_id != exclude_id)
        siblings = [
            GeozoneInterval(g.start_fraction, g.end_fraction, g.coefficient)
            for g in self._session.exec(query).all()
        ]
        if overlaps(start_fraction, end_fraction, siblings):
            raise GeozoneOverlapError(
                "Участок пересекается с уже размеченным на этом маршруте."
            )

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()


__all__ = [
    "SqlCatalogRepository",
    "assignment_title",
]
