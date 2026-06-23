from __future__ import annotations

from fastapi import APIRouter


healthcheck_router = APIRouter(tags=["Service"])


@healthcheck_router.get("/healthcheck")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
