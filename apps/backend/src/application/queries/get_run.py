from __future__ import annotations

from dataclasses import dataclass

from application.common.dto.pipeline_run import PipelineRunDTO
from application.interfaces.pipeline_run_repository import PipelineRunRepository
from application.queries.list_runs import pipeline_run_to_dto


@dataclass(frozen=True)
class GetRunQuery:
    run_id: str


class GetRunHandler:
    def __init__(self, repository: PipelineRunRepository) -> None:
        self._repository = repository

    def __call__(self, query: GetRunQuery) -> PipelineRunDTO:
        return pipeline_run_to_dto(self._repository.get_run(query.run_id))

