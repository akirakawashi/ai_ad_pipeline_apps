from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from application.common.dto.pipeline_run import RunObjectsDTO, RunSummaryDTO, RunTimelineDTO
from domain.entities.pipeline_run import PipelineRun, RunArtifact


class PipelineRunRepository(Protocol):
    def list_runs(self) -> list[PipelineRun]:
        raise NotImplementedError

    def get_run(self, run_id: str) -> PipelineRun:
        raise NotImplementedError

    def list_artifacts(self, run_id: str) -> list[RunArtifact]:
        raise NotImplementedError

    def get_artifact_path(self, run_id: str, relative_path: str) -> Path:
        raise NotImplementedError

    def get_summary(self, run_id: str) -> RunSummaryDTO:
        raise NotImplementedError

    def get_objects(self, run_id: str, limit: int | None = None) -> RunObjectsDTO:
        raise NotImplementedError

    def get_timeline(self, run_id: str, bucket_seconds: int) -> RunTimelineDTO:
        raise NotImplementedError

    def get_overlay(self, run_id: str) -> dict[str, Any]:
        raise NotImplementedError

