from __future__ import annotations

from fastapi import APIRouter, Depends, Path

from application.services.catalog_service import CatalogService
from presentation.http.dependencies import get_catalog_service
from presentation.http.dto.response import (
    BatchResponse,
    BatchSummaryResponse,
    OkResponse,
    PipelineRunResponse,
)


router = APIRouter(prefix="/batches", tags=["Batches"])


@router.get("/{batch_id}", response_model=OkResponse[BatchResponse])
def get_batch(
    batch_id: str = Path(description="Идентификатор пачки"),
    service: CatalogService = Depends(get_catalog_service),
) -> OkResponse[BatchResponse]:
    result = service.get_batch(batch_id)
    return OkResponse(data=BatchResponse.model_validate(result))


@router.get("/{batch_id}/runs", response_model=OkResponse[list[PipelineRunResponse]])
def list_batch_runs(
    batch_id: str = Path(description="Идентификатор пачки"),
    service: CatalogService = Depends(get_catalog_service),
) -> OkResponse[list[PipelineRunResponse]]:
    result = service.list_batch_runs(batch_id)
    return OkResponse(
        data=[PipelineRunResponse.model_validate(run) for run in result]
    )


@router.get("/{batch_id}/summary", response_model=OkResponse[BatchSummaryResponse])
def get_batch_summary(
    batch_id: str = Path(description="Идентификатор пачки"),
    service: CatalogService = Depends(get_catalog_service),
) -> OkResponse[BatchSummaryResponse]:
    result = service.get_batch_summary(batch_id)
    return OkResponse(data=BatchSummaryResponse.model_validate(result))
