from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Path, Query

from application.services.pipeline_run_service import PipelineRunService
from presentation.http.dependencies import get_run_service
from presentation.http.dto.response import (
    ArtifactUrlResponse,
    CreateRunRequest,
    CreateRunResponse,
    OkResponse,
    PaginatedRunsResponse,
    PipelineRunResponse,
    PlaybackResponse,
    RunArtifactResponse,
    RunObjectsResponse,
    RunSummaryResponse,
    RunTimelineResponse,
)


router = APIRouter(prefix="/runs", tags=["Pipeline Runs"])


@router.post("", response_model=OkResponse[CreateRunResponse], status_code=201)
def create_run(
    request: CreateRunRequest,
    service: PipelineRunService = Depends(get_run_service),
) -> OkResponse[CreateRunResponse]:
    result = service.create_run(
        file_name=request.file_name,
        content_type=request.content_type,
        size_bytes=request.size_bytes,
    )
    return OkResponse(data=CreateRunResponse.model_validate(result))


@router.post(
    "/{run_id}/upload-complete",
    response_model=OkResponse[PipelineRunResponse],
)
def complete_upload(
    run_id: str = Path(description="Pipeline run id"),
    service: PipelineRunService = Depends(get_run_service),
) -> OkResponse[PipelineRunResponse]:
    result = service.complete_upload(run_id)
    return OkResponse(data=PipelineRunResponse.model_validate(result))


@router.get("", response_model=OkResponse[PaginatedRunsResponse])
def list_runs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    service: PipelineRunService = Depends(get_run_service),
) -> OkResponse[PaginatedRunsResponse]:
    result = service.list_runs(
        page=page,
        page_size=page_size,
        status=status,
    )
    return OkResponse(data=PaginatedRunsResponse.model_validate(result))


@router.get(
    "/{run_id}",
    response_model=OkResponse[PipelineRunResponse],
)
def get_run(
    run_id: str = Path(description="Pipeline run id"),
    service: PipelineRunService = Depends(get_run_service),
) -> OkResponse[PipelineRunResponse]:
    return OkResponse(
        data=PipelineRunResponse.model_validate(service.get_run(run_id))
    )


@router.get(
    "/{run_id}/status",
    response_model=OkResponse[PipelineRunResponse],
)
def get_run_status(
    run_id: str = Path(description="Pipeline run id"),
    service: PipelineRunService = Depends(get_run_service),
) -> OkResponse[PipelineRunResponse]:
    return OkResponse(
        data=PipelineRunResponse.model_validate(service.get_run(run_id))
    )


@router.get(
    "/{run_id}/summary",
    response_model=OkResponse[RunSummaryResponse],
)
def get_run_summary(
    run_id: str = Path(description="Pipeline run id"),
    service: PipelineRunService = Depends(get_run_service),
) -> OkResponse[RunSummaryResponse]:
    return OkResponse(
        data=RunSummaryResponse.model_validate(
            service.get_summary(run_id)
        )
    )


@router.get(
    "/{run_id}/objects",
    response_model=OkResponse[RunObjectsResponse],
)
def get_run_objects(
    run_id: str = Path(description="Pipeline run id"),
    limit: int | None = Query(default=100, ge=1, le=1000),
    service: PipelineRunService = Depends(get_run_service),
) -> OkResponse[RunObjectsResponse]:
    return OkResponse(
        data=RunObjectsResponse.model_validate(
            service.get_objects(run_id, limit=limit)
        )
    )


@router.get(
    "/{run_id}/timeline",
    response_model=OkResponse[RunTimelineResponse],
)
def get_run_timeline(
    run_id: str = Path(description="Pipeline run id"),
    bucket_seconds: int = Query(default=10, ge=1, le=300),
    service: PipelineRunService = Depends(get_run_service),
) -> OkResponse[RunTimelineResponse]:
    return OkResponse(
        data=RunTimelineResponse.model_validate(
            service.get_timeline(
                run_id,
                bucket_seconds=bucket_seconds,
            )
        )
    )


@router.get(
    "/{run_id}/overlay",
    response_model=OkResponse[dict[str, Any]],
)
def get_run_overlay(
    run_id: str = Path(description="Pipeline run id"),
    service: PipelineRunService = Depends(get_run_service),
) -> OkResponse[dict[str, Any]]:
    return OkResponse(data=service.get_overlay(run_id))


@router.get(
    "/{run_id}/playback",
    response_model=OkResponse[PlaybackResponse],
)
def get_run_playback(
    run_id: str = Path(description="Pipeline run id"),
    service: PipelineRunService = Depends(get_run_service),
) -> OkResponse[PlaybackResponse]:
    return OkResponse(
        data=PlaybackResponse.model_validate(service.get_playback(run_id))
    )


@router.get(
    "/{run_id}/artifacts",
    response_model=OkResponse[list[RunArtifactResponse]],
)
def get_run_artifacts(
    run_id: str = Path(description="Pipeline run id"),
    service: PipelineRunService = Depends(get_run_service),
) -> OkResponse[list[RunArtifactResponse]]:
    return OkResponse(
        data=[
            RunArtifactResponse.model_validate(item)
            for item in service.get_artifacts(run_id)
        ]
    )


@router.get(
    "/{run_id}/artifacts/{artifact_id}/url",
    response_model=OkResponse[ArtifactUrlResponse],
)
def get_artifact_url(
    run_id: str = Path(description="Pipeline run id"),
    artifact_id: str = Path(description="Artifact id"),
    service: PipelineRunService = Depends(get_run_service),
) -> OkResponse[ArtifactUrlResponse]:
    return OkResponse(
        data=ArtifactUrlResponse.model_validate(
            service.get_artifact_url(run_id, artifact_id)
        )
    )
