from __future__ import annotations

from dataclasses import dataclass

from application.common.dto.pipeline_run import PipelineRunDTO
from application.interfaces.pipeline_run_repository import PipelineRunRepository
from domain.entities.pipeline_run import PipelineRun


@dataclass(frozen=True)
class ListRunsQuery:
    pass


class ListRunsHandler:
    def __init__(self, repository: PipelineRunRepository) -> None:
        self._repository = repository

    def __call__(self, _: ListRunsQuery) -> list[PipelineRunDTO]:
        return [pipeline_run_to_dto(run) for run in self._repository.list_runs()]


def pipeline_run_to_dto(run: PipelineRun) -> PipelineRunDTO:
    return PipelineRunDTO(
        run_id=run.run_id,
        source_name=run.source_name,
        source_path=run.source_path,
        input_type=run.input_type,
        fps=run.fps,
        frame_count=run.frame_count,
        frame_stride=run.frame_stride,
        duration_sec=run.duration_sec,
        width=run.width,
        height=run.height,
        created_at=run.created_at,
        has_overlay=run.has_overlay,
        has_viewer=run.has_viewer,
        has_report=run.has_report,
        has_annotated_video=run.has_annotated_video,
    )

