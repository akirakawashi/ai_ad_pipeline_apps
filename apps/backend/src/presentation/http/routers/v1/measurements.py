from __future__ import annotations

from fastapi import APIRouter, Depends, Path

from application.services.catalog_service import CatalogService
from presentation.http.dependencies import get_catalog_service
from presentation.http.dto.response import (
    MeasurementResponse,
    MeasurementSummaryResponse,
    OkResponse,
    PipelineRunResponse,
)

router = APIRouter(prefix="/measurements", tags=["Measurements"])


@router.get("/{measurement_id}", response_model=OkResponse[MeasurementResponse])
def get_measurement(
    measurement_id: str = Path(description="Идентификатор замера"),
    service: CatalogService = Depends(get_catalog_service),
) -> OkResponse[MeasurementResponse]:
    result = service.get_measurement(measurement_id)
    return OkResponse(data=MeasurementResponse.model_validate(result))


@router.get("/{measurement_id}/runs", response_model=OkResponse[list[PipelineRunResponse]])
def list_measurement_runs(
    measurement_id: str = Path(description="Идентификатор замера"),
    service: CatalogService = Depends(get_catalog_service),
) -> OkResponse[list[PipelineRunResponse]]:
    result = service.list_measurement_runs(measurement_id)
    return OkResponse(
        data=[PipelineRunResponse.model_validate(run) for run in result]
    )


@router.get("/{measurement_id}/summary", response_model=OkResponse[MeasurementSummaryResponse])
def get_measurement_summary(
    measurement_id: str = Path(description="Идентификатор замера"),
    service: CatalogService = Depends(get_catalog_service),
) -> OkResponse[MeasurementSummaryResponse]:
    result = service.get_measurement_summary(measurement_id)
    return OkResponse(data=MeasurementSummaryResponse.model_validate(result))
