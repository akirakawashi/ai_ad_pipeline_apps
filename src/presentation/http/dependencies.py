from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from fastapi import Depends
from sqlmodel import Session

from application.services.ad_catalog_service import AdCatalogService
from application.services.auth_service import AuthService
from application.services.catalog_service import CatalogService
from application.services.pipeline_run_service import PipelineRunService
from application.services.processing_job_service import ProcessingJobService
from application.services.user_service import UserService
from infrastructure.auth.keycloak import KeycloakIdentityProvider
from infrastructure.catalog.parser import ExcelCatalogParser
from infrastructure.database.session import get_db_session
from infrastructure.repositories.sql_ad_catalog_repository import (
    SqlAdCatalogRepository,
)
from infrastructure.repositories.sql_auth_repository import SqlAuthRepository
from infrastructure.repositories.sql_catalog_repository import SqlCatalogRepository
from infrastructure.repositories.sql_pipeline_run_repository import (
    SqlPipelineRunRepository,
)
from infrastructure.repositories.sql_user_repository import SqlUserRepository
from infrastructure.storage.minio_storage import MinioStorage
from settings.factory import get_settings


@lru_cache
def get_object_storage() -> MinioStorage:
    return MinioStorage(get_settings().object_storage)


def get_session() -> Generator[Session, None, None]:
    yield from get_db_session()


def get_run_service(
    session: Session = Depends(get_session),
    storage: MinioStorage = Depends(get_object_storage),
) -> PipelineRunService:
    return PipelineRunService(
        SqlPipelineRunRepository(session),
        storage,
    )


def get_processing_job_service(
    session: Session = Depends(get_session),
    storage: MinioStorage = Depends(get_object_storage),
) -> ProcessingJobService:
    repository = SqlPipelineRunRepository(session)
    return ProcessingJobService(
        repository,
        storage,
        PipelineRunService(repository, storage),
    )


def get_catalog_service(
    session: Session = Depends(get_session),
    storage: MinioStorage = Depends(get_object_storage),
) -> CatalogService:
    return CatalogService(
        SqlCatalogRepository(session),
        PipelineRunService(SqlPipelineRunRepository(session), storage),
    )


def get_ad_catalog_service(
    session: Session = Depends(get_session),
) -> AdCatalogService:
    # Разбор файлов — без состояния, отдельный экземпляр ничего не стоит.
    return AdCatalogService(SqlAdCatalogRepository(session), ExcelCatalogParser())


def get_user_service(
    session: Session = Depends(get_session),
) -> UserService:
    return UserService(SqlUserRepository(session))


@lru_cache
def get_identity_provider() -> KeycloakIdentityProvider:
    """Один на процесс: внутри кэш ключей JWKS, и ради него всё и кэшируется.

    Ключи realm меняются примерно никогда, а новый экземпляр на каждый запрос
    означал бы поход в Keycloak за JWKS на каждый вход.
    """
    return KeycloakIdentityProvider(get_settings().auth)


def get_auth_service(
    session: Session = Depends(get_session),
    provider: KeycloakIdentityProvider = Depends(get_identity_provider),
) -> AuthService:
    return AuthService(SqlAuthRepository(session), provider, get_settings().auth)
