from __future__ import annotations

from fastapi import APIRouter, Depends, File, Path, Query, Request, Response, UploadFile

from application.services.catalog_service import CatalogService
from presentation.http.dependencies import get_catalog_service
from presentation.http.dto.response import (
    AssignmentResponse,
    CityDetailResponse,
    CityResponse,
    CreateAssignmentRequest,
    CreateCityRequest,
    CreateRouteRequest,
    OkResponse,
    PaginatedAssignmentsResponse,
    RouteResponse,
    RouteSummaryResponse,
    UpdateCityRequest,
    UpdateRouteRequest,
)

router = APIRouter(prefix="/cities", tags=["Catalog"])

# Геометрия меняется редко, но её нельзя кэшировать «навсегда»: залили новый
# слой — карта должна увидеть его сразу. must-revalidate заставляет браузер
# спросить с If-None-Match, и на неизменившейся геометрии он получит 304 без
# полутора мегабайт тела.
GEOMETRY_CACHE_CONTROL = "private, max-age=0, must-revalidate"


def _geometry_response(
    request: Request,
    response: Response,
    version: str,
    geometry: dict,
) -> Response | OkResponse[dict]:
    """Общий хвост обоих геометрических GET: ETag и 304."""
    etag = f'W/"{version}"'
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=304,
            headers={"ETag": etag, "Cache-Control": GEOMETRY_CACHE_CONTROL},
        )
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = GEOMETRY_CACHE_CONTROL
    return OkResponse(data=geometry)


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


@router.post("", response_model=OkResponse[CityResponse], status_code=201)
def create_city(
    payload: CreateCityRequest,
    service: CatalogService = Depends(get_catalog_service),
) -> OkResponse[CityResponse]:
    result = service.create_city(
        slug=payload.slug,
        name=payload.name,
        region=payload.region,
        display_order=payload.display_order,
    )
    return OkResponse(data=CityResponse.model_validate(result))


@router.patch("/{city_slug}", response_model=OkResponse[CityDetailResponse])
def update_city(
    payload: UpdateCityRequest,
    city_slug: str = Path(description="Слаг города"),
    service: CatalogService = Depends(get_catalog_service),
) -> OkResponse[CityDetailResponse]:
    result = service.update_city(city_slug, fields=payload.changed_fields())
    return OkResponse(data=CityDetailResponse.model_validate(result))


@router.delete("/{city_slug}", status_code=204)
def deactivate_city(
    city_slug: str = Path(description="Слаг города"),
    service: CatalogService = Depends(get_catalog_service),
) -> None:
    """Деактивация, а не удаление: у заданий каскад на маршруты города."""
    service.deactivate_city(city_slug)


@router.put(
    "/{city_slug}/roads-geometry",
    response_model=OkResponse[CityDetailResponse],
)
def set_city_roads_geometry(
    city_slug: str = Path(description="Слаг города"),
    file: UploadFile = File(description="geojson дорожного слоя"),
    service: CatalogService = Depends(get_catalog_service),
) -> OkResponse[CityDetailResponse]:
    """Заливает дорожный слой и пересчитывает рамку города по нему.

    Синхронный обработчик: файл читается целиком в память, как и в каталоге.
    Полтора мегабайта — не повод разводить стриминг.
    """
    result = service.set_roads_geometry(city_slug, content=file.file.read())
    return OkResponse(data=CityDetailResponse.model_validate(result))


@router.get("/{city_slug}/roads-geometry", response_model=OkResponse[dict])
def get_city_roads_geometry(
    request: Request,
    response: Response,
    city_slug: str = Path(description="Слаг города"),
    service: CatalogService = Depends(get_catalog_service),
) -> Response | OkResponse[dict]:
    result = service.get_roads_geometry(city_slug)
    return _geometry_response(request, response, result.version, result.geometry)


@router.post(
    "/{city_slug}/routes",
    response_model=OkResponse[RouteResponse],
    status_code=201,
)
def create_route(
    payload: CreateRouteRequest,
    city_slug: str = Path(description="Слаг города"),
    service: CatalogService = Depends(get_catalog_service),
) -> OkResponse[RouteResponse]:
    result = service.create_route(
        city_slug=city_slug,
        slug=payload.slug,
        name=payload.name,
        color_label=payload.color_label,
        color_hex=payload.color_hex,
        description=payload.description,
        display_order=payload.display_order,
    )
    return OkResponse(data=RouteResponse.model_validate(result))


@router.patch(
    "/{city_slug}/routes/{route_slug}",
    response_model=OkResponse[RouteResponse],
)
def update_route(
    payload: UpdateRouteRequest,
    city_slug: str = Path(description="Слаг города"),
    route_slug: str = Path(description="Слаг маршрута в пределах города"),
    service: CatalogService = Depends(get_catalog_service),
) -> OkResponse[RouteResponse]:
    result = service.update_route(
        city_slug,
        route_slug,
        fields=payload.changed_fields(),
    )
    return OkResponse(data=RouteResponse.model_validate(result))


@router.delete("/{city_slug}/routes/{route_slug}", status_code=204)
def deactivate_route(
    city_slug: str = Path(description="Слаг города"),
    route_slug: str = Path(description="Слаг маршрута в пределах города"),
    service: CatalogService = Depends(get_catalog_service),
) -> None:
    """Маршрут пропадает из выбора, его задания и съёмки остаются."""
    service.deactivate_route(city_slug, route_slug)


@router.put(
    "/{city_slug}/routes/{route_slug}/geometry",
    response_model=OkResponse[RouteResponse],
)
def set_route_geometry(
    city_slug: str = Path(description="Слаг города"),
    route_slug: str = Path(description="Слаг маршрута в пределах города"),
    file: UploadFile = File(description="geojson линии маршрута"),
    service: CatalogService = Depends(get_catalog_service),
) -> OkResponse[RouteResponse]:
    result = service.set_route_geometry(city_slug, route_slug, content=file.file.read())
    return OkResponse(data=RouteResponse.model_validate(result))


@router.get(
    "/{city_slug}/routes/{route_slug}/geometry",
    response_model=OkResponse[dict],
)
def get_route_geometry(
    request: Request,
    response: Response,
    city_slug: str = Path(description="Слаг города"),
    route_slug: str = Path(description="Слаг маршрута в пределах города"),
    service: CatalogService = Depends(get_catalog_service),
) -> Response | OkResponse[dict]:
    result = service.get_route_geometry(city_slug, route_slug)
    return _geometry_response(request, response, result.version, result.geometry)


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
