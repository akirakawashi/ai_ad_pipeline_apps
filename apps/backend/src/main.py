from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from infrastructure.storage.minio_storage import MinioStorage
from presentation.http.exception_handlers import setup_exception_handlers
from presentation.http.routers.healthcheck import healthcheck_router
from presentation.http.routers.v1.router import api_v1_router
from settings.factory import ConfigFactory


config = ConfigFactory()


@asynccontextmanager
async def lifespan(_: FastAPI):
    storage = MinioStorage(config.object_storage)
    storage.ensure_bucket()
    yield


def include_routers(application: FastAPI) -> None:
    application.include_router(healthcheck_router)
    application.include_router(
        api_v1_router,
        prefix=config.app.api_v1_prefix,
    )


def setup_middlewares(application: FastAPI) -> None:
    application.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors.allow_origins,
        allow_credentials=config.cors.allow_credentials,
        allow_methods=config.cors.allow_methods,
        allow_headers=config.cors.allow_headers,
    )
    if config.app.trusted_hosts and config.app.trusted_hosts != ["*"]:
        application.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=config.app.trusted_hosts,
        )


def create_app() -> FastAPI:
    application = FastAPI(
        title=config.app.app_name,
        version=config.app.app_version,
        debug=config.app.debug,
        lifespan=lifespan,
    )
    include_routers(application)
    setup_middlewares(application)
    setup_exception_handlers(application)
    return application


app = create_app()
