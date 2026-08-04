from __future__ import annotations

from fastapi import APIRouter

from presentation.http.routers.internal.processing_jobs import (
    router as processing_jobs_router,
)

internal_v1_router = APIRouter()
internal_v1_router.include_router(processing_jobs_router)
