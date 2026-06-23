from __future__ import annotations

from dataclasses import dataclass

from application.common.dto.pipeline_run import RunTimelineDTO
from application.interfaces.pipeline_run_repository import PipelineRunRepository


@dataclass(frozen=True)
class GetRunTimelineQuery:
    run_id: str
    bucket_seconds: int = 10


class GetRunTimelineHandler:
    def __init__(self, repository: PipelineRunRepository) -> None:
        self._repository = repository

    def __call__(self, query: GetRunTimelineQuery) -> RunTimelineDTO:
        return self._repository.get_timeline(query.run_id, query.bucket_seconds)

