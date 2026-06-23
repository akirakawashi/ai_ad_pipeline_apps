from __future__ import annotations

from dataclasses import dataclass

from application.common.dto.pipeline_run import RunSummaryDTO
from application.interfaces.pipeline_run_repository import PipelineRunRepository


@dataclass(frozen=True)
class GetRunSummaryQuery:
    run_id: str


class GetRunSummaryHandler:
    def __init__(self, repository: PipelineRunRepository) -> None:
        self._repository = repository

    def __call__(self, query: GetRunSummaryQuery) -> RunSummaryDTO:
        return self._repository.get_summary(query.run_id)

