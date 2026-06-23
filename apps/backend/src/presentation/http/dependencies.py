from __future__ import annotations

from functools import lru_cache

from application.queries.get_run import GetRunHandler
from application.queries.get_run_objects import GetRunObjectsHandler
from application.queries.get_run_overlay import GetRunOverlayHandler
from application.queries.get_run_summary import GetRunSummaryHandler
from application.queries.get_run_timeline import GetRunTimelineHandler
from application.queries.list_runs import ListRunsHandler
from infrastructure.repositories.file_pipeline_run_repository import FilePipelineRunRepository
from settings.factory import ConfigFactory


@lru_cache(maxsize=1)
def get_config() -> ConfigFactory:
    return ConfigFactory()


@lru_cache(maxsize=1)
def get_pipeline_run_repository() -> FilePipelineRunRepository:
    config = get_config()
    return FilePipelineRunRepository(config.pipeline_outputs.output_dir)


def get_list_runs_handler() -> ListRunsHandler:
    return ListRunsHandler(get_pipeline_run_repository())


def get_run_handler() -> GetRunHandler:
    return GetRunHandler(get_pipeline_run_repository())


def get_run_summary_handler() -> GetRunSummaryHandler:
    return GetRunSummaryHandler(get_pipeline_run_repository())


def get_run_objects_handler() -> GetRunObjectsHandler:
    return GetRunObjectsHandler(get_pipeline_run_repository())


def get_run_timeline_handler() -> GetRunTimelineHandler:
    return GetRunTimelineHandler(get_pipeline_run_repository())


def get_run_overlay_handler() -> GetRunOverlayHandler:
    return GetRunOverlayHandler(get_pipeline_run_repository())

