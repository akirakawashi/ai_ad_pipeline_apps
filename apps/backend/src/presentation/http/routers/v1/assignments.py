from __future__ import annotations

from fastapi import APIRouter, Depends, Path

from application.services.catalog_service import CatalogService
from presentation.http.dependencies import get_catalog_service
from presentation.http.dto.response import (
    AssignmentResponse,
    AssignmentSummaryResponse,
    OkResponse,
    PipelineRunResponse,
    UpdateAssignmentRequest,
)

router = APIRouter(prefix="/assignments", tags=["Assignments"])


@router.get("/{assignment_id}", response_model=OkResponse[AssignmentResponse])
def get_assignment(
    assignment_id: str = Path(description="Идентификатор задания"),
    service: CatalogService = Depends(get_catalog_service),
) -> OkResponse[AssignmentResponse]:
    result = service.get_assignment(assignment_id)
    return OkResponse(data=AssignmentResponse.model_validate(result))


@router.patch("/{assignment_id}", response_model=OkResponse[AssignmentResponse])
def update_assignment(
    payload: UpdateAssignmentRequest,
    assignment_id: str = Path(description="Идентификатор задания"),
    service: CatalogService = Depends(get_catalog_service),
) -> OkResponse[AssignmentResponse]:
    result = service.update_assignment(assignment_id, fields=payload.changed_fields())
    return OkResponse(data=AssignmentResponse.model_validate(result))


@router.get("/{assignment_id}/runs", response_model=OkResponse[list[PipelineRunResponse]])
def list_assignment_runs(
    assignment_id: str = Path(description="Идентификатор задания"),
    service: CatalogService = Depends(get_catalog_service),
) -> OkResponse[list[PipelineRunResponse]]:
    result = service.list_assignment_runs(assignment_id)
    return OkResponse(
        data=[PipelineRunResponse.model_validate(run) for run in result]
    )


@router.get("/{assignment_id}/summary", response_model=OkResponse[AssignmentSummaryResponse])
def get_assignment_summary(
    assignment_id: str = Path(description="Идентификатор задания"),
    service: CatalogService = Depends(get_catalog_service),
) -> OkResponse[AssignmentSummaryResponse]:
    result = service.get_assignment_summary(assignment_id)
    return OkResponse(data=AssignmentSummaryResponse.model_validate(result))
