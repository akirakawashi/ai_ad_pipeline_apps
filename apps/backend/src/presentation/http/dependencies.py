from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from fastapi import Depends
from sqlmodel import Session

from application.services.pipeline_run_service import PipelineRunService
from infrastructure.database.session import get_db_session
from infrastructure.repositories.sql_pipeline_run_repository import (
    SqlPipelineRunRepository,
)
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
