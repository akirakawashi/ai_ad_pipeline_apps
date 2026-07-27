from __future__ import annotations

from fastapi import APIRouter, Depends, Path

from application.services.catalog_service import CatalogService
from presentation.http.dependencies import get_catalog_service
from presentation.http.dto.response import (
    CreateGeozoneRequest,
    GeozoneResponse,
    OkResponse,
    UpdateGeozoneRequest,
)

# Без префикса: список и создание живут под маршрутом, правка и удаление —
# плоско по идентификатору участка. Один роутер держит их вместе.
router = APIRouter(tags=["Geozones"])


@router.get(
    "/cities/{city_slug}/routes/{route_slug}/geozones",
    response_model=OkResponse[list[GeozoneResponse]],
)
def list_route_geozones(
    city_slug: str = Path(description="Слаг города"),
    route_slug: str = Path(description="Слаг маршрута в пределах города"),
    service: CatalogService = Depends(get_catalog_service),
) -> OkResponse[list[GeozoneResponse]]:
    result = service.list_geozones(city_slug=city_slug, route_slug=route_slug)
    return OkResponse(data=[GeozoneResponse.model_validate(zone) for zone in result])


@router.post(
    "/cities/{city_slug}/routes/{route_slug}/geozones",
    response_model=OkResponse[GeozoneResponse],
    status_code=201,
)
def create_route_geozone(
    payload: CreateGeozoneRequest,
    city_slug: str = Path(description="Слаг города"),
    route_slug: str = Path(description="Слаг маршрута в пределах города"),
    service: CatalogService = Depends(get_catalog_service),
) -> OkResponse[GeozoneResponse]:
    result = service.create_geozone(
        city_slug=city_slug,
        route_slug=route_slug,
        name=payload.name,
        start_fraction=payload.start_fraction,
        end_fraction=payload.end_fraction,
        coefficient=payload.coefficient,
    )
    return OkResponse(data=GeozoneResponse.model_validate(result))


@router.patch("/geozones/{geozone_id}", response_model=OkResponse[GeozoneResponse])
def update_geozone(
    payload: UpdateGeozoneRequest,
    geozone_id: str = Path(description="Идентификатор участка"),
    service: CatalogService = Depends(get_catalog_service),
) -> OkResponse[GeozoneResponse]:
    result = service.update_geozone(geozone_id, fields=payload.changed_fields())
    return OkResponse(data=GeozoneResponse.model_validate(result))


@router.delete("/geozones/{geozone_id}", status_code=204)
def delete_geozone(
    geozone_id: str = Path(description="Идентификатор участка"),
    service: CatalogService = Depends(get_catalog_service),
) -> None:
    service.delete_geozone(geozone_id)
