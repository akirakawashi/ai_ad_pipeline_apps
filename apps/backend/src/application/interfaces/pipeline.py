from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Protocol

from application.common.dto import PipelineArtifactDTO, PipelineRunDTO
from domain.entities import PipelineArtifactType, PipelineRunStage, PipelineRunStatus
from domain.geozones import GeozoneInterval


class ObjectStat(Protocol):
    size: int


class RunObjectStorage(Protocol):
    def presigned_put(
        self,
        object_key: str,
        *,
        expires_seconds: int | None = None,
    ) -> str: ...

    def presigned_get(
        self,
        object_key: str,
        *,
        expires_seconds: int | None = None,
    ) -> str: ...

    def stat(self, object_key: str) -> ObjectStat: ...

    def read_bytes(self, object_key: str) -> bytes: ...

    def read_text(self, object_key: str) -> str: ...


class WorkerObjectStorage(Protocol):
    def ensure_bucket(self) -> None: ...

    def download_file(self, object_key: str, destination: Path) -> None: ...

    def upload_file(
        self,
        source: Path,
        object_key: str,
        *,
        content_type: str | None = None,
    ) -> object: ...


class PipelineRunRepository(Protocol):
    def create(
        self,
        *,
        run_id: str,
        source_name: str,
        source_object_key: str,
        content_type: str | None,
        size_bytes: int,
        assignment_id: str,
        shot_started_at: datetime,
        operator_user_id: str | None = None,
    ) -> PipelineRunDTO: ...

    def update_shooting(
        self,
        run_id: str,
        *,
        fields: dict[str, object],
    ) -> PipelineRunDTO | None:
        """Правит реквизиты съёмки. None — съёмки нет."""
        ...

    def list_runs(
        self,
        *,
        page: int,
        page_size: int,
        status: PipelineRunStatus | None = None,
        city_id: str | None = None,
        route_id: str | None = None,
        assignment_id: str | None = None,
    ) -> tuple[list[PipelineRunDTO], int]: ...

    def lock_assignment(self, assignment_id: str) -> bool: ...

    def count_assignment_runs(self, assignment_id: str) -> int: ...

    def get(
        self,
        run_id: str,
        *,
        with_artifacts: bool = True,
        with_events: bool = False,
        include_hidden: bool = False,
    ) -> PipelineRunDTO | None:
        """Съёмка для показа. None — нет её или её задание скрыто.

        `include_hidden` — только для дозавершения начатой загрузки."""
        ...

    def get_geozone_intervals(self, run_id: str) -> list[GeozoneInterval]:
        """Участки значимости маршрута съёмки. Пусто — β = 1.0 у всех."""
        ...

    def mark_upload_complete(
        self,
        run_id: str,
        *,
        actual_size_bytes: int,
    ) -> PipelineRunDTO | None: ...

    def add_artifact(
        self,
        *,
        run_id: str,
        artifact_type: PipelineArtifactType,
        object_key: str,
        content_type: str,
        size_bytes: int,
    ) -> PipelineArtifactDTO: ...

    def claim_next(self, worker_id: str) -> PipelineRunDTO | None: ...

    def update_progress(
        self,
        run_id: str,
        *,
        stage: PipelineRunStage,
        progress: int,
        message: str | None,
        create_event: bool = False,
    ) -> None: ...

    def mark_completed(
        self,
        run_id: str,
        *,
        fps: float,
        frame_count: int,
        frame_stride: int,
        width: int,
        height: int,
    ) -> None: ...

    def mark_failed(
        self,
        run_id: str,
        *,
        error_code: str,
        error_message: str,
    ) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
