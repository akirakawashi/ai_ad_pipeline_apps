from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import FileResponse

from application.queries.get_run import GetRunHandler, GetRunQuery
from application.queries.get_run_objects import GetRunObjectsHandler, GetRunObjectsQuery
from application.queries.get_run_overlay import GetRunOverlayHandler, GetRunOverlayQuery
from application.queries.get_run_summary import GetRunSummaryHandler, GetRunSummaryQuery
from application.queries.get_run_timeline import GetRunTimelineHandler, GetRunTimelineQuery
from application.queries.list_runs import ListRunsHandler, ListRunsQuery
from infrastructure.repositories.file_pipeline_run_repository import FilePipelineRunRepository
from presentation.http.dependencies import (
    get_list_runs_handler,
    get_pipeline_run_repository,
    get_run_handler,
    get_run_objects_handler,
    get_run_overlay_handler,
    get_run_summary_handler,
    get_run_timeline_handler,
)
from presentation.http.dto.response import (
    OkResponse,
    PipelineRunResponse,
    RunObjectsResponse,
    RunSummaryResponse,
    RunTimelineResponse,
)


router = APIRouter(prefix="/runs", tags=["Pipeline Runs"])


@router.get("", response_model=OkResponse[list[PipelineRunResponse]])
async def list_runs(
    handler: ListRunsHandler = Depends(get_list_runs_handler),
) -> OkResponse[list[PipelineRunResponse]]:
    result = handler(ListRunsQuery())
    return OkResponse(data=[PipelineRunResponse.model_validate(asdict(item)) for item in result])


@router.get("/{run_id}", response_model=OkResponse[PipelineRunResponse])
async def get_run(
    run_id: str = Path(description="Pipeline run id"),
    handler: GetRunHandler = Depends(get_run_handler),
) -> OkResponse[PipelineRunResponse]:
    result = handler(GetRunQuery(run_id=run_id))
    return OkResponse(data=PipelineRunResponse.model_validate(asdict(result)))


@router.get("/{run_id}/summary", response_model=OkResponse[RunSummaryResponse])
async def get_run_summary(
    run_id: str = Path(description="Pipeline run id"),
    handler: GetRunSummaryHandler = Depends(get_run_summary_handler),
) -> OkResponse[RunSummaryResponse]:
    result = handler(GetRunSummaryQuery(run_id=run_id))
    return OkResponse(data=RunSummaryResponse.model_validate(asdict(result)))


@router.get("/{run_id}/objects", response_model=OkResponse[RunObjectsResponse])
async def get_run_objects(
    run_id: str = Path(description="Pipeline run id"),
    limit: int | None = Query(default=None, ge=1, le=1000, description="Maximum number of objects"),
    handler: GetRunObjectsHandler = Depends(get_run_objects_handler),
) -> OkResponse[RunObjectsResponse]:
    result = handler(GetRunObjectsQuery(run_id=run_id, limit=limit))
    return OkResponse(data=RunObjectsResponse.model_validate(asdict(result)))


@router.get("/{run_id}/timeline", response_model=OkResponse[RunTimelineResponse])
async def get_run_timeline(
    run_id: str = Path(description="Pipeline run id"),
    bucket_seconds: int = Query(default=10, ge=1, le=300, description="Timeline aggregation bucket"),
    handler: GetRunTimelineHandler = Depends(get_run_timeline_handler),
) -> OkResponse[RunTimelineResponse]:
    result = handler(GetRunTimelineQuery(run_id=run_id, bucket_seconds=bucket_seconds))
    return OkResponse(data=RunTimelineResponse.model_validate(asdict(result)))


@router.get("/{run_id}/overlay", response_model=OkResponse[dict[str, Any]])
async def get_run_overlay(
    run_id: str = Path(description="Pipeline run id"),
    handler: GetRunOverlayHandler = Depends(get_run_overlay_handler),
) -> OkResponse[dict[str, Any]]:
    return OkResponse(data=handler(GetRunOverlayQuery(run_id=run_id)))


@router.get("/{run_id}/files/{relative_path:path}")
async def get_run_file(
    run_id: str = Path(description="Pipeline run id"),
    relative_path: str = Path(description="Artifact path inside run directory"),
    repository: FilePipelineRunRepository = Depends(get_pipeline_run_repository),
) -> FileResponse:
    path = repository.get_artifact_path(run_id, relative_path)
    return FileResponse(path)

