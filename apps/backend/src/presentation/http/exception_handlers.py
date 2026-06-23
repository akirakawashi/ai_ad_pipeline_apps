from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from minio.error import S3Error

from application.services.pipeline_run_service import (
    InvalidVideoError,
    PipelineRunNotFoundError,
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

    @app.exception_handler(InvalidVideoError)
    async def invalid_video_handler(
        _: Request,
        exc: InvalidVideoError,
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
            content={"detail": f"Object storage error: {exc.code}"},
        )
