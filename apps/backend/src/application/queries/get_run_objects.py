from __future__ import annotations

from dataclasses import dataclass

from application.common.dto.pipeline_run import RunObjectsDTO
from application.interfaces.pipeline_run_repository import PipelineRunRepository


@dataclass(frozen=True)
class GetRunObjectsQuery:
    run_id: str
    limit: int | None = None


class GetRunObjectsHandler:
    def __init__(self, repository: PipelineRunRepository) -> None:
        self._repository = repository

    def __call__(self, query: GetRunObjectsQuery) -> RunObjectsDTO:
        return self._repository.get_objects(query.run_id, query.limit)

