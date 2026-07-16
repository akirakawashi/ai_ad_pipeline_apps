from __future__ import annotations

from application.common.dto import CityRefDTO, RouteRefDTO, RunBatchRefDTO
from infrastructure.database.models import City, PipelineRun, Route, RouteBatch


def batch_title(batch: RouteBatch) -> str:
    """Единственное место, где выводится отображаемое имя пачки."""
    if batch.title:
        return batch.title
    if batch.created_at is None:
        return f"Пачка №{batch.sequence_number}"
    return f"Пачка №{batch.sequence_number} · {batch.created_at:%d.%m.%Y}"


def city_ref(city: City) -> CityRefDTO:
    return CityRefDTO(id=city.cities_id, slug=city.slug, name=city.name)


def route_ref(route: Route) -> RouteRefDTO:
    return RouteRefDTO(
        id=route.routes_id,
        slug=route.slug,
        name=route.name,
        color_hex=route.color_hex,
    )


def batch_ref(run: PipelineRun) -> RunBatchRefDTO | None:
    """Ссылка на пачку для карточки видео. None — «Без маршрута».

    Требует, чтобы связь batch → route → city была загружена заранее:
    зовётся только при _run_to_dto(with_batch=True).
    """
    batch = run.batch
    if batch is None or batch.route is None or batch.route.city is None:
        return None
    return RunBatchRefDTO(
        batch_id=batch.route_batches_id,
        sequence_number=batch.sequence_number,
        title=batch_title(batch),
        route=route_ref(batch.route),
        city=city_ref(batch.route.city),
    )
