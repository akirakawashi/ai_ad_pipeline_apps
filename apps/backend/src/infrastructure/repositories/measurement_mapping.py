from __future__ import annotations

from application.common.dto import CityRefDTO, RouteRefDTO, RunMeasurementRefDTO
from infrastructure.database.models import City, PipelineRun, Route, RouteMeasurement


def measurement_title(measurement: RouteMeasurement) -> str:
    """Единственное место, где выводится отображаемое имя замера."""
    if measurement.title:
        return measurement.title
    if measurement.created_at is None:
        return f"Замер №{measurement.sequence_number}"
    return f"Замер №{measurement.sequence_number} · {measurement.created_at:%d.%m.%Y}"


def city_ref(city: City) -> CityRefDTO:
    return CityRefDTO(id=city.cities_id, slug=city.slug, name=city.name)


def route_ref(route: Route) -> RouteRefDTO:
    return RouteRefDTO(
        id=route.routes_id,
        slug=route.slug,
        name=route.name,
        color_hex=route.color_hex,
    )


def measurement_ref(run: PipelineRun) -> RunMeasurementRefDTO | None:
    """Ссылка на замер для карточки видео. None — «Без маршрута».

    Требует, чтобы связь measurement → route → city была загружена заранее:
    зовётся только при _run_to_dto(with_measurement=True).
    """
    measurement = run.measurement
    if measurement is None or measurement.route is None or measurement.route.city is None:
        return None
    return RunMeasurementRefDTO(
        measurement_id=measurement.route_measurements_id,
        sequence_number=measurement.sequence_number,
        title=measurement_title(measurement),
        route=route_ref(measurement.route),
        city=city_ref(measurement.route.city),
    )
