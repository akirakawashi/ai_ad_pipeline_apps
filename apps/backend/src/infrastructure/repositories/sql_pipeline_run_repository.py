from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import noload, selectinload
from sqlmodel import Session, select

from infrastructure.database.models import (
    PipelineArtifact,
    PipelineRun,
    PipelineRunEvent,
)


class SqlPipelineRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        run_id: str,
        source_name: str,
        source_object_key: str,
        content_type: str | None,
        size_bytes: int,
    ) -> PipelineRun:
        run = PipelineRun(
            pipeline_runs_id=run_id,
            source_name=source_name,
            source_object_key=source_object_key,
            source_content_type=content_type,
            source_size_bytes=size_bytes,
            status="uploading",
            stage="upload",
            progress=0,
            status_message="Ждём загрузку видео",
        )
        self._session.add(run)
        self._session.flush()
        self.add_event(
            run.pipeline_runs_id,
            stage="upload",
            progress=0,
            message="Обработка создана",
        )
        self._session.commit()
        self._session.refresh(run)
        return run

    def list_runs(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None = None,
    ) -> tuple[list[PipelineRun], int]:
        filters = []
        if status:
            filters.append(PipelineRun.status == status)

        total = self._session.exec(
            select(func.count(PipelineRun.pipeline_runs_id)).where(*filters)
        ).one()
        statement = (
            select(PipelineRun)
            .where(*filters)
            .options(
                selectinload(PipelineRun.artifacts),
                noload(PipelineRun.events),
            )
            .order_by(PipelineRun.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        runs = self._session.exec(statement).all()
        return list(runs), int(total)

    def get(
        self,
        run_id: str,
        *,
        with_artifacts: bool = True,
        with_events: bool = False,
    ) -> PipelineRun | None:
        statement = select(PipelineRun).where(PipelineRun.pipeline_runs_id == run_id)
        if with_artifacts:
            statement = statement.options(selectinload(PipelineRun.artifacts))
        else:
            statement = statement.options(noload(PipelineRun.artifacts))
        if with_events:
            statement = statement.options(selectinload(PipelineRun.events))
        else:
            statement = statement.options(noload(PipelineRun.events))
        return self._session.exec(statement).one_or_none()

    def mark_upload_complete(
        self,
        run: PipelineRun,
        *,
        actual_size_bytes: int,
    ) -> None:
        run.source_size_bytes = actual_size_bytes
        run.status = "queued"
        run.stage = "queued"
        run.progress = 0
        run.status_message = "Видео загружено. Анализ скоро начнётся"
        run.upload_completed_at = datetime.now(timezone.utc)
        self.add_event(
            run.pipeline_runs_id,
            stage="queued",
            progress=0,
            message=run.status_message,
        )
        self._session.commit()

    def add_artifact(
        self,
        *,
        run_id: str,
        artifact_type: str,
        object_key: str,
        content_type: str,
        size_bytes: int,
    ) -> PipelineArtifact:
        artifact = PipelineArtifact(
            pipeline_runs_id=run_id,
            artifact_type=artifact_type,
            object_key=object_key,
            content_type=content_type,
            size_bytes=size_bytes,
        )
        self._session.add(artifact)
        self._session.flush()
        return artifact

    def add_event(
        self,
        run_id: str,
        *,
        stage: str,
        progress: int,
        message: str | None,
    ) -> None:
        self._session.add(
            PipelineRunEvent(
                pipeline_runs_id=run_id,
                stage=stage,
                progress=progress,
                message=message,
            )
        )

    def commit(self) -> None:
        self._session.commit()

    def claim_next(self, worker_id: str) -> PipelineRun | None:
        statement = (
            select(PipelineRun)
            .where(PipelineRun.status == "queued")
            .order_by(PipelineRun.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        run = self._session.exec(statement).first()
        if run is None:
            self._session.rollback()
            return None

        run.status = "processing"
        run.stage = "preparing"
        run.progress = 1
        run.status_message = "Готовим видео к анализу"
        run.worker_id = worker_id
        run.started_at = datetime.now(timezone.utc)
        self.add_event(
            run.pipeline_runs_id,
            stage=run.stage,
            progress=run.progress,
            message=run.status_message,
        )
        self._session.commit()
        self._session.refresh(run)
        return run

    def update_progress(
        self,
        run_id: str,
        *,
        stage: str,
        progress: int,
        message: str | None,
        create_event: bool = False,
    ) -> None:
        run = self.get(run_id, with_artifacts=False)
        if run is None:
            return
        run.stage = stage
        run.progress = max(0, min(100, progress))
        run.status_message = message
        if create_event:
            self.add_event(
                run_id,
                stage=stage,
                progress=run.progress,
                message=message,
            )
        self._session.commit()

    def mark_completed(
        self,
        run_id: str,
        *,
        fps: float,
        frame_count: int,
        frame_stride: int,
        width: int,
        height: int,
    ) -> None:
        run = self.get(run_id, with_artifacts=False)
        if run is None:
            return
        run.status = "completed"
        run.stage = "completed"
        run.progress = 100
        run.status_message = "Анализ готов"
        run.fps = fps
        run.frame_count = frame_count
        run.frame_stride = frame_stride
        run.duration_sec = frame_count / fps if fps > 0 and frame_count > 0 else None
        run.width = width
        run.height = height
        run.completed_at = datetime.now(timezone.utc)
        self.add_event(
            run_id,
            stage="completed",
            progress=100,
            message=run.status_message,
        )
        self._session.commit()

    def mark_failed(
        self,
        run_id: str,
        *,
        error_code: str,
        error_message: str,
    ) -> None:
        self._session.rollback()
        run = self.get(run_id, with_artifacts=False)
        if run is None:
            return
        run.status = "processing_failed"
        run.stage = "failed"
        run.status_message = "Анализ остановился с ошибкой"
        run.error_code = error_code
        run.error_message = error_message
        run.completed_at = datetime.now(timezone.utc)
        self.add_event(
            run_id,
            stage="failed",
            progress=run.progress,
            message=run.status_message,
        )
        self._session.commit()
