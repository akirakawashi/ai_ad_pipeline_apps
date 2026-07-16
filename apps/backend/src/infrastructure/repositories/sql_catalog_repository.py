from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import noload, selectinload
from sqlmodel import Session, select

from application.common.dto import (
    CityDetailDTO,
    CityDTO,
    MeasurementStatusCountsDTO,
    PipelineRunDTO,
    RouteDTO,
    RouteMeasurementDTO,
)
from infrastructure.database.models import City, PipelineRun, Route, RouteMeasurement
from infrastructure.repositories.measurement_mapping import (
    city_ref,
    measurement_title,
    route_ref,
)
from infrastructure.repositories.sql_pipeline_run_repository import _run_to_dto


def _route_to_dto(
    route: Route,
    *,
    measurement_count: int = 0,
    video_count: int = 0,
) -> RouteDTO:
    return RouteDTO(
        id=route.routes_id,
        slug=route.slug,
        name=route.name,
        color_label=route.color_label,
        color_hex=route.color_hex,
        geojson_path=route.geojson_path,
        display_order=route.display_order,
        measurement_count=measurement_count,
        video_count=video_count,
    )


def _measurement_to_dto(
    measurement: RouteMeasurement,
    route: Route,
    city: City,
    *,
    video_count: int = 0,
    status_counts: MeasurementStatusCountsDTO | None = None,
) -> RouteMeasurementDTO:
    return RouteMeasurementDTO(
        id=measurement.route_measurements_id,
        sequence_number=measurement.sequence_number,
        title=measurement_title(measurement),
        route=route_ref(route),
        city=city_ref(city),
        video_count=video_count,
        status_counts=status_counts or MeasurementStatusCountsDTO(),
        created_at=measurement.created_at,
    )


class SqlCatalogRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # --- счётчики -------------------------------------------------------

    def _measurement_counts_by_route(self) -> dict[str, int]:
        rows = self._session.exec(
            select(RouteMeasurement.routes_id, func.count(RouteMeasurement.route_measurements_id))
            .group_by(RouteMeasurement.routes_id)
        ).all()
        return {routes_id: int(count) for routes_id, count in rows}

    def _video_counts_by_route(self) -> dict[str, int]:
        rows = self._session.exec(
            select(RouteMeasurement.routes_id, func.count(PipelineRun.pipeline_runs_id))
            .join(PipelineRun, PipelineRun.route_measurements_id == RouteMeasurement.route_measurements_id)
            .group_by(RouteMeasurement.routes_id)
        ).all()
        return {routes_id: int(count) for routes_id, count in rows}

    def _video_counts_by_measurement(self, measurement_ids: list[str]) -> dict[str, int]:
        if not measurement_ids:
            return {}
        rows = self._session.exec(
            select(PipelineRun.route_measurements_id, func.count(PipelineRun.pipeline_runs_id))
            .where(PipelineRun.route_measurements_id.in_(measurement_ids))
            .group_by(PipelineRun.route_measurements_id)
        ).all()
        return {measurement_id: int(count) for measurement_id, count in rows}

    def _status_counts_by_measurement(
        self,
        measurement_ids: list[str],
    ) -> dict[str, MeasurementStatusCountsDTO]:
        if not measurement_ids:
            return {}
        rows = self._session.exec(
            select(
                PipelineRun.route_measurements_id,
                PipelineRun.status,
                func.count(PipelineRun.pipeline_runs_id),
            )
            .where(PipelineRun.route_measurements_id.in_(measurement_ids))
            .group_by(PipelineRun.route_measurements_id, PipelineRun.status)
        ).all()
        result: dict[str, MeasurementStatusCountsDTO] = {}
        for measurement_id, status, count in rows:
            counts = result.setdefault(measurement_id, MeasurementStatusCountsDTO())
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

        measurement_rows = self._session.exec(
            select(Route.cities_id, func.count(RouteMeasurement.route_measurements_id))
            .join(RouteMeasurement, RouteMeasurement.routes_id == Route.routes_id)
            .group_by(Route.cities_id)
        ).all()
        measurement_counts = {cities_id: int(count) for cities_id, count in measurement_rows}

        video_rows = self._session.exec(
            select(Route.cities_id, func.count(PipelineRun.pipeline_runs_id))
            .join(RouteMeasurement, RouteMeasurement.routes_id == Route.routes_id)
            .join(
                PipelineRun,
                PipelineRun.route_measurements_id == RouteMeasurement.route_measurements_id,
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
                measurement_count=measurement_counts.get(city.cities_id, 0),
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

        measurement_counts = self._measurement_counts_by_route()
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
            measurement_count=sum(measurement_counts.get(r.routes_id, 0) for r in routes),
            video_count=sum(video_counts.get(r.routes_id, 0) for r in routes),
            routes=[
                _route_to_dto(
                    route,
                    measurement_count=measurement_counts.get(route.routes_id, 0),
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
            measurement_count=self._measurement_counts_by_route().get(route.routes_id, 0),
            video_count=self._video_counts_by_route().get(route.routes_id, 0),
        )

    # --- замера ------------------------------------------------------------

    def list_measurements(
        self,
        *,
        city_slug: str,
        route_slug: str,
        page: int,
        page_size: int,
    ) -> tuple[list[RouteMeasurementDTO], int]:
        route = self._get_route_model(city_slug, route_slug)
        if route is None:
            return [], 0
        city = route.city
        if city is None:
            return [], 0

        total = self._session.exec(
            select(func.count(RouteMeasurement.route_measurements_id)).where(
                RouteMeasurement.routes_id == route.routes_id
            )
        ).one()

        measurements = self._session.exec(
            select(RouteMeasurement)
            .where(RouteMeasurement.routes_id == route.routes_id)
            .order_by(RouteMeasurement.sequence_number.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()

        measurement_ids = [measurement.route_measurements_id for measurement in measurements]
        video_counts = self._video_counts_by_measurement(measurement_ids)
        status_counts = self._status_counts_by_measurement(measurement_ids)

        return [
            _measurement_to_dto(
                measurement,
                route,
                city,
                video_count=video_counts.get(measurement.route_measurements_id, 0),
                status_counts=status_counts.get(measurement.route_measurements_id),
            )
            for measurement in measurements
        ], int(total)

    def create_measurement(
        self,
        *,
        city_slug: str,
        route_slug: str,
    ) -> RouteMeasurementDTO | None:
        route = self._get_route_model(city_slug, route_slug)
        if route is None:
            return None

        # Блокируем строку маршрута: два одновременных POST сериализуются здесь
        # и получают разные номера. uq_route_measurements_route_sequence — подстраховка.
        self._session.exec(
            select(Route)
            .where(Route.routes_id == route.routes_id)
            .with_for_update()
        ).first()

        next_sequence = self._session.exec(
            select(
                func.coalesce(func.max(RouteMeasurement.sequence_number), 0) + 1
            ).where(RouteMeasurement.routes_id == route.routes_id)
        ).one()

        measurement = RouteMeasurement(
            routes_id=route.routes_id,
            sequence_number=int(next_sequence),
        )
        self._session.add(measurement)
        self._session.flush()
        self._session.refresh(measurement)

        city = route.city
        if city is None:
            return None
        return _measurement_to_dto(measurement, route, city)

    def _get_measurement_model(self, measurement_id: str) -> RouteMeasurement | None:
        return self._session.exec(
            select(RouteMeasurement)
            .where(RouteMeasurement.route_measurements_id == measurement_id)
            .options(selectinload(RouteMeasurement.route).selectinload(Route.city))
        ).first()

    def get_measurement(self, measurement_id: str) -> RouteMeasurementDTO | None:
        measurement = self._get_measurement_model(measurement_id)
        if measurement is None or measurement.route is None or measurement.route.city is None:
            return None
        return _measurement_to_dto(
            measurement,
            measurement.route,
            measurement.route.city,
            video_count=self._video_counts_by_measurement([measurement_id]).get(measurement_id, 0),
            status_counts=self._status_counts_by_measurement([measurement_id]).get(measurement_id),
        )

    def list_measurement_runs(self, measurement_id: str) -> list[PipelineRunDTO]:
        runs = self._session.exec(
            select(PipelineRun)
            .where(PipelineRun.route_measurements_id == measurement_id)
            .options(
                selectinload(PipelineRun.artifacts),
                noload(PipelineRun.events),
                noload(PipelineRun.measurement),
            )
            .order_by(PipelineRun.created_at)
        ).all()
        return [_run_to_dto(run) for run in runs]

    def lock_measurement(self, measurement_id: str) -> bool:
        """Блокирует строку замера. False, если замера нет."""
        measurement = self._session.exec(
            select(RouteMeasurement)
            .where(RouteMeasurement.route_measurements_id == measurement_id)
            .with_for_update()
        ).first()
        return measurement is not None

    def count_measurement_runs(self, measurement_id: str) -> int:
        total = self._session.exec(
            select(func.count(PipelineRun.pipeline_runs_id)).where(
                PipelineRun.route_measurements_id == measurement_id
            )
        ).one()
        return int(total)

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()


__all__ = [
    "SqlCatalogRepository",
    "measurement_title",
]
