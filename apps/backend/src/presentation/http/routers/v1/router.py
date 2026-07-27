from __future__ import annotations

from fastapi import APIRouter

from presentation.http.routers.v1.ad_catalog import router as ad_catalog_router
from presentation.http.routers.v1.cities import router as cities_router
from presentation.http.routers.v1.assignments import router as assignments_router
from presentation.http.routers.v1.geozones import router as geozones_router
from presentation.http.routers.v1.pipeline_runs import router as pipeline_runs_router
from presentation.http.routers.v1.users import router as users_router

api_v1_router = APIRouter()
api_v1_router.include_router(pipeline_runs_router)
api_v1_router.include_router(cities_router)
api_v1_router.include_router(assignments_router)
api_v1_router.include_router(geozones_router)
api_v1_router.include_router(ad_catalog_router)
api_v1_router.include_router(users_router)
