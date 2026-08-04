from __future__ import annotations

from fastapi import APIRouter, Depends, Path

from application.common.dto import (
    ProcessingArtifactInputDTO,
    ProcessingVideoMetadataDTO,
)
from application.services.processing_job_service import ProcessingJobService
from presentation.http.dependencies import get_processing_job_service
from presentation.http.dto.processing import (
    ProcessingClaimRequest,
    ProcessingCompleteRequest,
    ProcessingFailRequest,
    ProcessingJobResponse,
    ProcessingProgressRequest,
)
from presentation.http.dto.response import OkResponse
from presentation.http.processing_security import require_processing_service

router = APIRouter(
    prefix="/processing/jobs",
    tags=["Internal Processing"],
    dependencies=[Depends(require_processing_service)],
)


@router.post("/claim", response_model=OkResponse[ProcessingJobResponse | None])
def claim_job(
    _payload: ProcessingClaimRequest,
    service: ProcessingJobService = Depends(get_processing_job_service),
) -> OkResponse[ProcessingJobResponse | None]:
    run = service.claim_next()
    if run is None:
        return OkResponse(data=None)
    return OkResponse(
        data=ProcessingJobResponse(
            run_id=run.run_id,
            source_name=run.source_name,
            source_object_key=run.source_object_key,
            output_prefix=f"runs/{run.run_id}/artifacts",
        )
    )


@router.post("/{run_id}/progress", status_code=204)
def report_progress(
    payload: ProcessingProgressRequest,
    run_id: str = Path(max_length=36),
    service: ProcessingJobService = Depends(get_processing_job_service),
) -> None:
    service.report_progress(
        run_id,
        stage=payload.stage,
        progress=payload.progress,
        message=payload.message,
        create_event=payload.create_event,
    )


@router.post("/{run_id}/complete", status_code=204)
def complete_job(
    payload: ProcessingCompleteRequest,
    run_id: str = Path(max_length=36),
    service: ProcessingJobService = Depends(get_processing_job_service),
) -> None:
    service.complete(
        run_id,
        metadata=ProcessingVideoMetadataDTO.model_validate(payload.metadata),
        artifacts=[
            ProcessingArtifactInputDTO.model_validate(item) for item in payload.artifacts
        ],
    )


@router.post("/{run_id}/fail", status_code=204)
def fail_job(
    payload: ProcessingFailRequest,
    run_id: str = Path(max_length=36),
    service: ProcessingJobService = Depends(get_processing_job_service),
) -> None:
    service.fail(
        run_id,
        error_code=payload.error_code,
        error_message=payload.error_message,
    )
