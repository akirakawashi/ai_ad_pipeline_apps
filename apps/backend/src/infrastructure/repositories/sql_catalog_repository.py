from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import noload, selectinload
from sqlmodel import Session, select

from application.common.dto import (
    BatchStatusCountsDTO,
    CityDetailDTO,
    CityDTO,
    PipelineRunDTO,
    RouteBatchDTO,
    RouteDTO,
)
from infrastructure.database.models import City, PipelineRun, Route, RouteBatch
from infrastructure.repositories.batch_mapping import batch_title, city_ref, route_ref
from infrastructure.repositories.sql_pipeline_run_repository import _run_to_dto


def _route_to_dto(
    route: Route,
    *,
    batch_count: int = 0,
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
        batch_count=batch_count,
        video_count=video_count,
    )


def _batch_to_dto(
    batch: RouteBatch,
    route: Route,
    city: City,
    *,
    video_count: int = 0,
    status_counts: BatchStatusCountsDTO | None = None,
) -> RouteBatchDTO:
    return RouteBatchDTO(
        id=batch.route_batches_id,
        sequence_number=batch.sequence_number,
        title=batch_title(batch),
        route=route_ref(route),
        city=city_ref(city),
        video_count=video_count,
        status_counts=status_counts or BatchStatusCountsDTO(),
        created_at=batch.created_at,
    )


class SqlCatalogRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # --- счётчики -------------------------------------------------------

    def _batch_counts_by_route(self) -> dict[str, int]:
        rows = self._session.exec(
            select(RouteBatch.routes_id, func.count(RouteBatch.route_batches_id))
            .group_by(RouteBatch.routes_id)
        ).all()
        return {routes_id: int(count) for routes_id, count in rows}

    def _video_counts_by_route(self) -> dict[str, int]:
        rows = self._session.exec(
            select(RouteBatch.routes_id, func.count(PipelineRun.pipeline_runs_id))
            .join(PipelineRun, PipelineRun.route_batches_id == RouteBatch.route_batches_id)
            .group_by(RouteBatch.routes_id)
        ).all()
        return {routes_id: int(count) for routes_id, count in rows}

    def _video_counts_by_batch(self, batch_ids: list[str]) -> dict[str, int]:
        if not batch_ids:
            return {}
        rows = self._session.exec(
            select(PipelineRun.route_batches_id, func.count(PipelineRun.pipeline_runs_id))
            .where(PipelineRun.route_batches_id.in_(batch_ids))
            .group_by(PipelineRun.route_batches_id)
        ).all()
        return {batch_id: int(count) for batch_id, count in rows}

    def _status_counts_by_batch(
        self,
        batch_ids: list[str],
    ) -> dict[str, BatchStatusCountsDTO]:
        if not batch_ids:
            return {}
        rows = self._session.exec(
            select(
                PipelineRun.route_batches_id,
                PipelineRun.status,
                func.count(PipelineRun.pipeline_runs_id),
            )
            .where(PipelineRun.route_batches_id.in_(batch_ids))
            .group_by(PipelineRun.route_batches_id, PipelineRun.status)
        ).all()
        result: dict[str, BatchStatusCountsDTO] = {}
        for batch_id, status, count in rows:
            counts = result.setdefault(batch_id, BatchStatusCountsDTO())
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

        batch_rows = self._session.exec(
            select(Route.cities_id, func.count(RouteBatch.route_batches_id))
            .join(RouteBatch, RouteBatch.routes_id == Route.routes_id)
            .group_by(Route.cities_id)
        ).all()
        batch_counts = {cities_id: int(count) for cities_id, count in batch_rows}

        video_rows = self._session.exec(
            select(Route.cities_id, func.count(PipelineRun.pipeline_runs_id))
            .join(RouteBatch, RouteBatch.routes_id == Route.routes_id)
            .join(
                PipelineRun,
                PipelineRun.route_batches_id == RouteBatch.route_batches_id,
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
                batch_count=batch_counts.get(city.cities_id, 0),
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

        batch_counts = self._batch_counts_by_route()
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
            batch_count=sum(batch_counts.get(r.routes_id, 0) for r in routes),
            video_count=sum(video_counts.get(r.routes_id, 0) for r in routes),
            routes=[
                _route_to_dto(
                    route,
                    batch_count=batch_counts.get(route.routes_id, 0),
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
            batch_count=self._batch_counts_by_route().get(route.routes_id, 0),
            video_count=self._video_counts_by_route().get(route.routes_id, 0),
        )

    # --- пачки ------------------------------------------------------------

    def list_batches(
        self,
        *,
        city_slug: str,
        route_slug: str,
        page: int,
        page_size: int,
    ) -> tuple[list[RouteBatchDTO], int]:
        route = self._get_route_model(city_slug, route_slug)
        if route is None:
            return [], 0
        city = route.city
        if city is None:
            return [], 0

        total = self._session.exec(
            select(func.count(RouteBatch.route_batches_id)).where(
                RouteBatch.routes_id == route.routes_id
            )
        ).one()

        batches = self._session.exec(
            select(RouteBatch)
            .where(RouteBatch.routes_id == route.routes_id)
            .order_by(RouteBatch.sequence_number.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()

        batch_ids = [batch.route_batches_id for batch in batches]
        video_counts = self._video_counts_by_batch(batch_ids)
        status_counts = self._status_counts_by_batch(batch_ids)

        return [
            _batch_to_dto(
                batch,
                route,
                city,
                video_count=video_counts.get(batch.route_batches_id, 0),
                status_counts=status_counts.get(batch.route_batches_id),
            )
            for batch in batches
        ], int(total)

    def create_batch(
        self,
        *,
        city_slug: str,
        route_slug: str,
    ) -> RouteBatchDTO | None:
        route = self._get_route_model(city_slug, route_slug)
        if route is None:
            return None

        # Блокируем строку маршрута: два одновременных POST сериализуются здесь
        # и получают разные номера. uq_route_batches_route_sequence — подстраховка.
        self._session.exec(
            select(Route)
            .where(Route.routes_id == route.routes_id)
            .with_for_update()
        ).first()

        next_sequence = self._session.exec(
            select(
                func.coalesce(func.max(RouteBatch.sequence_number), 0) + 1
            ).where(RouteBatch.routes_id == route.routes_id)
        ).one()

        batch = RouteBatch(
            routes_id=route.routes_id,
            sequence_number=int(next_sequence),
        )
        self._session.add(batch)
        self._session.flush()
        self._session.refresh(batch)

        city = route.city
        if city is None:
            return None
        return _batch_to_dto(batch, route, city)

    def _get_batch_model(self, batch_id: str) -> RouteBatch | None:
        return self._session.exec(
            select(RouteBatch)
            .where(RouteBatch.route_batches_id == batch_id)
            .options(selectinload(RouteBatch.route).selectinload(Route.city))
        ).first()

    def get_batch(self, batch_id: str) -> RouteBatchDTO | None:
        batch = self._get_batch_model(batch_id)
        if batch is None or batch.route is None or batch.route.city is None:
            return None
        return _batch_to_dto(
            batch,
            batch.route,
            batch.route.city,
            video_count=self._video_counts_by_batch([batch_id]).get(batch_id, 0),
            status_counts=self._status_counts_by_batch([batch_id]).get(batch_id),
        )

    def list_batch_runs(self, batch_id: str) -> list[PipelineRunDTO]:
        runs = self._session.exec(
            select(PipelineRun)
            .where(PipelineRun.route_batches_id == batch_id)
            .options(
                selectinload(PipelineRun.artifacts),
                noload(PipelineRun.events),
                noload(PipelineRun.batch),
            )
            .order_by(PipelineRun.created_at)
        ).all()
        return [_run_to_dto(run) for run in runs]

    def lock_batch(self, batch_id: str) -> bool:
        """Блокирует строку пачки. False, если пачки нет."""
        batch = self._session.exec(
            select(RouteBatch)
            .where(RouteBatch.route_batches_id == batch_id)
            .with_for_update()
        ).first()
        return batch is not None

    def count_batch_runs(self, batch_id: str) -> int:
        total = self._session.exec(
            select(func.count(PipelineRun.pipeline_runs_id)).where(
                PipelineRun.route_batches_id == batch_id
            )
        ).one()
        return int(total)

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()


__all__ = [
    "SqlCatalogRepository",
    "batch_title",
]
