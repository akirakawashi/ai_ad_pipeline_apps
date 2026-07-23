from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from minio.error import S3Error

from application.exceptions import (
    AssignmentFullError,
    CatalogNotFoundError,
    InvalidAssignmentError,
    InvalidUserError,
    InvalidVideoError,
    PipelineRunNotFoundError,
    UserAlreadyExistsError,
)


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
