from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Path, Query, UploadFile

from application.services.ad_catalog_service import AdCatalogService, UploadedFile
from presentation.http.dependencies import get_ad_catalog_service
from presentation.http.security import require_admin
from presentation.http.dto.response import (
    AdStructureResponse,
    CatalogImportReportResponse,
    CatalogImportResponse,
    OkResponse,
    PaginatedAdStructuresResponse,
)

# Без префикса: загрузка и список живут под городом, действия над ревизией —
# плоско по её идентификатору. Один роутер держит их вместе, как у геозон.
router = APIRouter(tags=["Ad catalog"])

# Всё, что меняет каталог, — под админским паролем: одной кнопкой «Удалить»
# сносится ревизия на шесть сотен конструкций. Оба чтения остаются открытыми, и
# это не послабление: `list_catalog_imports` — единственный источник строки
# «Ревизия N · точек: X» на продуктовой странице каталога, а `list_ad_structures`
# и есть сама таблица, ради которой на страницу приходят.


@router.post(
    "/cities/{city_slug}/catalog/imports",
    response_model=OkResponse[CatalogImportReportResponse],
    status_code=201,
    dependencies=[Depends(require_admin)],
)
def upload_catalog_import(
    city_slug: str = Path(description="Слаг города"),
    files: list[UploadFile] = File(description="Файлы пака: xlsx, xls или csv"),
    uploaded_by_user_id: str = Form(description="Кто загрузил, из справочника"),
    service: AdCatalogService = Depends(get_ad_catalog_service),
) -> OkResponse[CatalogImportReportResponse]:
    """Разбирает пак и возвращает отчёт. Каталог при этом не меняется.

    Ручка синхронная намеренно: FastAPI выполнит её в пуле потоков, а работа с
    базой у нас синхронная. Байты читаем через `file.file` — тоже синхронно, и
    файл после ответа исчезает: временный спул за нас чистит Starlette.
    """
    payload = [
        UploadedFile(name=item.filename or "без имени", content=item.file.read())
        for item in files
    ]
    result = service.upload(
        city_slug=city_slug,
        uploaded_by_user_id=uploaded_by_user_id,
        files=payload,
    )
    return OkResponse(data=CatalogImportReportResponse.model_validate(result))


@router.post(
    "/catalog/imports/{import_id}/apply",
    response_model=OkResponse[CatalogImportResponse],
    dependencies=[Depends(require_admin)],
)
def apply_catalog_import(
    import_id: str = Path(description="Идентификатор загрузки"),
    service: AdCatalogService = Depends(get_ad_catalog_service),
) -> OkResponse[CatalogImportResponse]:
    """Делает пак текущей ревизией города: прежняя гаснет, эта зажигается."""
    result = service.apply(import_id)
    return OkResponse(data=CatalogImportResponse.model_validate(result))


@router.post(
    "/catalog/imports/{import_id}/restore",
    response_model=OkResponse[CatalogImportResponse],
    dependencies=[Depends(require_admin)],
)
def restore_catalog_import(
    import_id: str = Path(description="Идентификатор ревизии"),
    service: AdCatalogService = Depends(get_ad_catalog_service),
) -> OkResponse[CatalogImportResponse]:
    """Откат: снова показывать прежнюю ревизию. Данные не пересоздаются."""
    result = service.restore(import_id)
    return OkResponse(data=CatalogImportResponse.model_validate(result))


@router.delete(
    "/catalog/imports/{import_id}",
    status_code=204,
    dependencies=[Depends(require_admin)],
)
def delete_catalog_import(
    import_id: str = Path(description="Идентификатор загрузки или ревизии"),
    service: AdCatalogService = Depends(get_ad_catalog_service),
) -> None:
    """Отменяет неприменённый пак или убирает старую ревизию."""
    service.delete(import_id)


@router.get(
    "/cities/{city_slug}/catalog/imports",
    response_model=OkResponse[list[CatalogImportResponse]],
)
def list_catalog_imports(
    city_slug: str = Path(description="Слаг города"),
    service: AdCatalogService = Depends(get_ad_catalog_service),
) -> OkResponse[list[CatalogImportResponse]]:
    result = service.list_imports(city_slug)
    return OkResponse(
        data=[CatalogImportResponse.model_validate(item) for item in result]
    )


@router.get(
    "/cities/{city_slug}/ad-structures",
    response_model=OkResponse[PaginatedAdStructuresResponse],
)
def list_ad_structures(
    city_slug: str = Path(description="Слаг города"),
    search: str | None = Query(default=None, description="Поиск по адресу"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=1000),
    service: AdCatalogService = Depends(get_ad_catalog_service),
) -> OkResponse[PaginatedAdStructuresResponse]:
    """Конструкции текущей ревизии города."""
    result = service.list_structures(
        city_slug=city_slug,
        search=search,
        page=page,
        page_size=page_size,
    )
    return OkResponse(data=PaginatedAdStructuresResponse.model_validate(result))


__all__ = ["router", "AdStructureResponse"]
