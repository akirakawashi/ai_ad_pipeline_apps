from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query

from application.services.catalog_service import CatalogService
from presentation.http.dependencies import get_catalog_service
from presentation.http.dto.response import (
    AssignmentResponse,
    CityDetailResponse,
    CityResponse,
    CreateAssignmentRequest,
    OkResponse,
    PaginatedAssignmentsResponse,
    RouteSummaryResponse,
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
    "/{city_slug}/routes/{route_slug}/assignments",
    response_model=OkResponse[PaginatedAssignmentsResponse],
)
def list_route_assignments(
    city_slug: str = Path(description="Слаг города"),
    route_slug: str = Path(description="Слаг маршрута в пределах города"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    service: CatalogService = Depends(get_catalog_service),
) -> OkResponse[PaginatedAssignmentsResponse]:
    result = service.list_assignments(
        city_slug=city_slug,
        route_slug=route_slug,
        page=page,
        page_size=page_size,
    )
    return OkResponse(data=PaginatedAssignmentsResponse.model_validate(result))


@router.get(
    "/{city_slug}/routes/{route_slug}/summary",
    response_model=OkResponse[RouteSummaryResponse],
)
def get_route_summary(
    city_slug: str = Path(description="Слаг города"),
    route_slug: str = Path(description="Слаг маршрута в пределах города"),
    service: CatalogService = Depends(get_catalog_service),
) -> OkResponse[RouteSummaryResponse]:
    result = service.get_route_summary(city_slug, route_slug)
    return OkResponse(data=RouteSummaryResponse.model_validate(result))


@router.post(
    "/{city_slug}/routes/{route_slug}/assignments",
    response_model=OkResponse[AssignmentResponse],
    status_code=201,
)
def create_route_assignment(
    payload: CreateAssignmentRequest,
    city_slug: str = Path(description="Слаг города"),
    route_slug: str = Path(description="Слаг маршрута в пределах города"),
    service: CatalogService = Depends(get_catalog_service),
) -> OkResponse[AssignmentResponse]:
    result = service.create_assignment(
        city_slug=city_slug,
        route_slug=route_slug,
        title=payload.title,
        description=payload.description,
        planned_start_at=payload.planned_start_at,
        planned_end_at=payload.planned_end_at,
        author_user_id=payload.author_user_id,
    )
    return OkResponse(data=AssignmentResponse.model_validate(result))
