from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.interfaces.pipeline_run_repository import PipelineRunRepository


@dataclass(frozen=True)
class GetRunOverlayQuery:
    run_id: str


class GetRunOverlayHandler:
    def __init__(self, repository: PipelineRunRepository) -> None:
        self._repository = repository

    def __call__(self, query: GetRunOverlayQuery) -> dict[str, Any]:
        return self._repository.get_overlay(query.run_id)

