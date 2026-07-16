from __future__ import annotations

from fastapi import APIRouter

from presentation.http.routers.v1.cities import router as cities_router
from presentation.http.routers.v1.measurements import router as measurements_router
from presentation.http.routers.v1.pipeline_runs import router as pipeline_runs_router

api_v1_router = APIRouter()
api_v1_router.include_router(pipeline_runs_router)
api_v1_router.include_router(cities_router)
api_v1_router.include_router(measurements_router)
