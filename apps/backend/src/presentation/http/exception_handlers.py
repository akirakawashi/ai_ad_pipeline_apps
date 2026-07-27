from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from minio.error import S3Error
from sqlalchemy.exc import IntegrityError

from application.exceptions import (
    AssignmentFullError,
    CatalogImportStateError,
    CatalogNotFoundError,
    DuplicateSlugError,
    GeozoneOverlapError,
    InvalidAssignmentError,
    InvalidCatalogFileError,
    InvalidGeometryError,
    InvalidGeozoneError,
    InvalidUserError,
    InvalidVideoError,
    PipelineRunNotFoundError,
    UserAlreadyExistsError,
)

# SQLSTATE PostgreSQL: ссылка на несуществующую строку и нарушение уникальности.
FOREIGN_KEY_VIOLATION = "23503"
UNIQUE_VIOLATION = "23505"


def setup_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(PipelineRunNotFoundError)
    async def run_not_found_handler(
        _: Request,
        exc: PipelineRunNotFoundError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"detail": str(exc)},
        )

    @app.exception_handler(CatalogNotFoundError)
    async def catalog_not_found_handler(
        _: Request,
        exc: CatalogNotFoundError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"detail": str(exc)},
        )

    @app.exception_handler(AssignmentFullError)
    async def assignment_full_handler(
        _: Request,
        exc: AssignmentFullError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"detail": str(exc)},
        )

    @app.exception_handler(UserAlreadyExistsError)
    async def user_exists_handler(
        _: Request,
        exc: UserAlreadyExistsError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"detail": str(exc)},
        )

    @app.exception_handler(InvalidVideoError)
    async def invalid_video_handler(
        _: Request,
        exc: InvalidVideoError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"detail": str(exc)},
        )

    @app.exception_handler(InvalidUserError)
    async def invalid_user_handler(
        _: Request,
        exc: InvalidUserError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"detail": str(exc)},
        )

    @app.exception_handler(InvalidAssignmentError)
    async def invalid_assignment_handler(
        _: Request,
        exc: InvalidAssignmentError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"detail": str(exc)},
        )

    @app.exception_handler(InvalidGeozoneError)
    async def invalid_geozone_handler(
        _: Request,
        exc: InvalidGeozoneError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"detail": str(exc)},
        )

    @app.exception_handler(GeozoneOverlapError)
    async def geozone_overlap_handler(
        _: Request,
        exc: GeozoneOverlapError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"detail": str(exc)},
        )

    @app.exception_handler(InvalidCatalogFileError)
    async def invalid_catalog_file_handler(
        _: Request,
        exc: InvalidCatalogFileError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"detail": str(exc)},
        )

    @app.exception_handler(InvalidGeometryError)
    async def invalid_geometry_handler(
        _: Request,
        exc: InvalidGeometryError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"detail": str(exc)},
        )

    @app.exception_handler(DuplicateSlugError)
    async def duplicate_slug_handler(
        _: Request,
        exc: DuplicateSlugError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"detail": str(exc)},
        )

    @app.exception_handler(CatalogImportStateError)
    async def catalog_import_state_handler(
        _: Request,
        exc: CatalogImportStateError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"detail": str(exc)},
        )

    @app.exception_handler(IntegrityError)
    async def integrity_handler(
        _: Request,
        exc: IntegrityError,
    ) -> JSONResponse:
        """Последний рубеж перед 500 на нарушениях целостности.

        Наружу нельзя отдавать str(exc): SQLAlchemy кладёт туда текст запроса
        и все параметры. Различаем по SQLSTATE — сообщения разные по смыслу.
        """
        sqlstate = getattr(exc.orig, "sqlstate", None)
        if sqlstate == FOREIGN_KEY_VIOLATION:
            return JSONResponse(
                status_code=400,
                content={"detail": "Ссылка на запись, которой не существует."},
            )
        if sqlstate == UNIQUE_VIOLATION:
            return JSONResponse(
                status_code=409,
                content={"detail": "Такая запись уже есть."},
            )
        return JSONResponse(
            status_code=409,
            content={"detail": "Не удалось сохранить: данные противоречат друг другу."},
        )

    @app.exception_handler(S3Error)
    async def object_storage_handler(
        _: Request,
        exc: S3Error,
    ) -> JSONResponse:
        status_code = 404 if exc.code in {"NoSuchKey", "NoSuchBucket"} else 502
        return JSONResponse(
            status_code=status_code,
            content={"detail": "Не удалось получить файл из хранилища."},
        )
