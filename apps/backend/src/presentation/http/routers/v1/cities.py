from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query

from application.services.catalog_service import CatalogService
from presentation.http.dependencies import get_catalog_service
from presentation.http.dto.response import (
    CityDetailResponse,
    CityResponse,
    MeasurementResponse,
    OkResponse,
    PaginatedMeasurementsResponse,
)

router = APIRouter(prefix="/cities", tags=["Catalog"])


@router.get("", response_model=OkResponse[list[CityResponse]])
def list_cities(
    service: CatalogService = Depends(get_catalog_service),
) -> OkResponse[list[CityResponse]]:
    result = service.list_cities()
    return OkResponse(data=[CityResponse.model_validate(city) for city in result])


@router.get("/{city_slug}", response_model=OkResponse[CityDetailResponse])
def get_city(
    city_slug: str = Path(description="Слаг города, например simferopol"),
    service: CatalogService = Depends(get_catalog_service),
) -> OkResponse[CityDetailResponse]:
    result = service.get_city(city_slug)
    return OkResponse(data=CityDetailResponse.model_validate(result))


@router.get(
    "/{city_slug}/routes/{route_slug}/measurements",
    response_model=OkResponse[PaginatedMeasurementsResponse],
)
def list_route_measurements(
    city_slug: str = Path(description="Слаг города"),
    route_slug: str = Path(description="Слаг маршрута в пределах города"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    service: CatalogService = Depends(get_catalog_service),
) -> OkResponse[PaginatedMeasurementsResponse]:
    result = service.list_measurements(
        city_slug=city_slug,
        route_slug=route_slug,
        page=page,
        page_size=page_size,
    )
    return OkResponse(data=PaginatedMeasurementsResponse.model_validate(result))


@router.post(
    "/{city_slug}/routes/{route_slug}/measurements",
    response_model=OkResponse[MeasurementResponse],
    status_code=201,
)
def create_route_measurement(
    city_slug: str = Path(description="Слаг города"),
    route_slug: str = Path(description="Слаг маршрута в пределах города"),
    service: CatalogService = Depends(get_catalog_service),
) -> OkResponse[MeasurementResponse]:
    result = service.create_measurement(city_slug=city_slug, route_slug=route_slug)
    return OkResponse(data=MeasurementResponse.model_validate(result))
