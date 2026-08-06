from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from infrastructure.storage.minio_storage import MinioStorage
from presentation.http.exception_handlers import setup_exception_handlers
from presentation.http.routers.healthcheck import healthcheck_router
from presentation.http.routers.internal import internal_v1_router
from presentation.http.routers.v1.router import api_v1_router
from settings.auth import warn_if_unusable
from settings.factory import get_settings

config = get_settings()

# Непригодная настройка входа не роняет запуск: отказ всего сервиса ради одной
# незаполненной переменной — лекарство хуже болезни. Пишем в лог, а человек на
# экране входа увидит внятную причину вместо кнопки в никуда.
_auth_problem = warn_if_unusable(config.auth)
if _auth_problem:
    logging.getLogger("ai_ad.auth").warning(_auth_problem)


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
    application.include_router(
        internal_v1_router,
        prefix="/internal/v1",
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
