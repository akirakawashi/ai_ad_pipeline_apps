from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from domain.exceptions.pipeline_run import (
    InvalidPipelineArtifactPathError,
    PipelineArtifactNotFoundError,
    PipelineRunDataError,
    PipelineRunNotFoundError,
)


def setup_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(PipelineRunNotFoundError)
    async def run_not_found_handler(_: Request, exc: PipelineRunNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(PipelineArtifactNotFoundError)
    async def artifact_not_found_handler(_: Request, exc: PipelineArtifactNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(InvalidPipelineArtifactPathError)
    async def invalid_artifact_path_handler(_: Request, exc: InvalidPipelineArtifactPathError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(PipelineRunDataError)
    async def run_data_error_handler(_: Request, exc: PipelineRunDataError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

