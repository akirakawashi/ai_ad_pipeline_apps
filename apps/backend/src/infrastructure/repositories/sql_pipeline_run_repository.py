from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import noload, selectinload
from sqlmodel import Session, select

from application.common.dto import (
    PipelineArtifactDTO,
    PipelineRunDTO,
    PipelineRunEventDTO,
)
from domain.entities import PipelineArtifactType, PipelineRunStage, PipelineRunStatus
from domain.geozones import GeozoneInterval
from infrastructure.database.models import (
    Assignment,
    City,
    PipelineArtifact,
    PipelineRun,
    PipelineRunEvent,
    Route,
    RouteGeozone,
)
from infrastructure.repositories.assignment_mapping import assignment_ref, user_ref


def _status_value(status: PipelineRunStatus) -> str:
    return status.value


def _stage_value(stage: PipelineRunStage) -> str:
    return stage.value


def _artifact_type(artifact_type: str) -> PipelineArtifactType:
    try:
        return PipelineArtifactType(artifact_type)
    except ValueError:
        return PipelineArtifactType.ARTIFACT


def _status(status: str) -> PipelineRunStatus:
    return PipelineRunStatus(status)


def _stage(stage: str) -> PipelineRunStage:
    return PipelineRunStage(stage)


def _artifact_to_dto(artifact: PipelineArtifact) -> PipelineArtifactDTO:
    return PipelineArtifactDTO(
        id=artifact.pipeline_artifacts_id,
        run_id=artifact.pipeline_runs_id,
        artifact_type=_artifact_type(artifact.artifact_type),
        object_key=artifact.object_key,
        content_type=artifact.content_type,
        size_bytes=artifact.size_bytes,
        created_at=artifact.created_at,
    )


def _event_to_dto(event: PipelineRunEvent) -> PipelineRunEventDTO:
    return PipelineRunEventDTO(
        id=event.pipeline_run_events_id,
        run_id=event.pipeline_runs_id,
        stage=_stage(event.stage),
        progress=event.progress,
        message=event.message,
        created_at=event.created_at,
    )


def _shot_finished_at(run: PipelineRun) -> datetime | None:
    """Конец съёмки не хранится: старт плюс длительность самого видео.

    Так поле физически не может разойтись с файлом. Пока видео не обработано,
    длительность неизвестна — возвращаем None, интерфейс покажет прочерк.
    """
    if run.shot_started_at is None or not run.duration_sec:
        return None
    return run.shot_started_at + timedelta(seconds=run.duration_sec)


def _run_to_dto(run: PipelineRun, *, with_refs: bool = False) -> PipelineRunDTO:
    # with_refs=True только там, где связи загружены через selectinload.
    # Воркер зовёт эту функцию на detached-инстансах — там assignment
    # и operator трогать нельзя.
    return PipelineRunDTO(
        assignment=assignment_ref(run) if with_refs else None,
        operator=user_ref(run.operator) if with_refs else None,
        shot_started_at=run.shot_started_at,
        shot_finished_at=_shot_finished_at(run),
        run_id=run.pipeline_runs_id,
        source_name=run.source_name,
        source_object_key=run.source_object_key,
        source_content_type=run.source_content_type,
        source_size_bytes=run.source_size_bytes,
        status=_status(run.status),
        stage=_stage(run.stage),
        progress=run.progress,
        status_message=run.status_message,
        error_code=run.error_code,
        error_message=run.error_message,
        fps=run.fps,
        frame_count=run.frame_count,
        frame_stride=run.frame_stride,
        duration_sec=run.duration_sec,
        width=run.width,
        height=run.height,
        created_at=run.created_at,
        upload_completed_at=run.upload_completed_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        updated_at=run.updated_at,
        artifacts=[_artifact_to_dto(item) for item in run.artifacts],
        events=[_event_to_dto(item) for item in run.events],
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
        assignment_id: str | None = None,
        shot_started_at: datetime | None = None,
        operator_user_id: str | None = None,
    ) -> PipelineRunDTO:
        run = PipelineRun(
            pipeline_runs_id=run_id,
            source_name=source_name,
            source_object_key=source_object_key,
            source_content_type=content_type,
            source_size_bytes=size_bytes,
            assignments_id=assignment_id,
            shot_started_at=shot_started_at,
            operator_users_id=operator_user_id,
            status=PipelineRunStatus.UPLOADING.value,
            stage=PipelineRunStage.UPLOAD.value,
            progress=0,
            status_message="Ждём загрузку видео",
        )
        self._session.add(run)
        self._session.flush()
        self.add_event(
            run.pipeline_runs_id,
            stage=PipelineRunStage.UPLOAD,
            progress=0,
            message="Обработка создана",
        )
        self._session.flush()
        return _run_to_dto(run)

    def list_runs(
        self,
        *,
        page: int,
        page_size: int,
        status: PipelineRunStatus | None = None,
        city_id: str | None = None,
        route_id: str | None = None,
        assignment_id: str | None = None,
        assigned: bool | None = None,
    ) -> tuple[list[PipelineRunDTO], int]:
        filters = []
        if status:
            filters.append(PipelineRun.status == _status_value(status))
        if assignment_id:
            filters.append(PipelineRun.assignments_id == assignment_id)
        if assigned is not None:
            if assigned:
                filters.append(PipelineRun.assignments_id.is_not(None))
            else:
                filters.append(PipelineRun.assignments_id.is_(None))
        if route_id or city_id:
            # Маршрут и город достаём подзапросом по цепочке assignment → route → city,
            # чтобы не денормализовать их в pipeline_runs.
            assignment_ids = select(Assignment.assignments_id).join(
                Route, Route.routes_id == Assignment.routes_id
            )
            if route_id:
                assignment_ids = assignment_ids.where(Route.routes_id == route_id)
            if city_id:
                assignment_ids = assignment_ids.where(Route.cities_id == city_id)
            filters.append(PipelineRun.assignments_id.in_(assignment_ids))

        total = self._session.exec(
            select(func.count(PipelineRun.pipeline_runs_id)).where(*filters)
        ).one()
        statement = (
            select(PipelineRun)
            .where(*filters)
            .options(
                selectinload(PipelineRun.artifacts),
                noload(PipelineRun.events),
                selectinload(PipelineRun.assignment)
                .selectinload(Assignment.route)
                .defer(Route.geometry)
                .selectinload(Route.city)
                .defer(City.roads_geometry),
            )
            .order_by(PipelineRun.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        runs = self._session.exec(statement).all()
        return [_run_to_dto(run, with_refs=True) for run in runs], int(total)

    def get(
        self,
        run_id: str,
        *,
        with_artifacts: bool = True,
        with_events: bool = False,
    ) -> PipelineRunDTO | None:
        run = self._get_model(
            run_id,
            with_artifacts=with_artifacts,
            with_events=with_events,
            with_refs=True,
        )
        return _run_to_dto(run, with_refs=True) if run else None

    def get_geozone_intervals(self, run_id: str) -> list[GeozoneInterval]:
        """Участки значимости маршрута этой съёмки — вход для расчёта β.

        Пусто, если съёмка без задания (маршрута нет) или маршрут не размечен;
        тогда β = 1.0 у всех объектов. Цепочка: run → assignment → route → зоны.
        """
        rows = self._session.exec(
            select(
                RouteGeozone.start_fraction,
                RouteGeozone.end_fraction,
                RouteGeozone.coefficient,
            )
            .join(Route, Route.routes_id == RouteGeozone.routes_id)
            .join(Assignment, Assignment.routes_id == Route.routes_id)
            .join(PipelineRun, PipelineRun.assignments_id == Assignment.assignments_id)
            .where(PipelineRun.pipeline_runs_id == run_id)
        ).all()
        return [GeozoneInterval(start, end, coef) for start, end, coef in rows]

    def update_shooting(
        self,
        run_id: str,
        *,
        fields: dict[str, object],
    ) -> PipelineRunDTO | None:
        """Правит реквизиты съёмки. Статус и стадию обработки не трогает."""
        run = self._get_model(run_id, with_artifacts=True, with_refs=True)
        if run is None:
            return None
        for name, value in fields.items():
            setattr(run, name, value)
        self._session.add(run)
        self._session.flush()
        self._session.refresh(run)
        return _run_to_dto(run, with_refs=True)

    def mark_upload_complete(
        self,
        run_id: str,
        *,
        actual_size_bytes: int,
    ) -> PipelineRunDTO | None:
        run = self._get_model(run_id, with_artifacts=True)
        if run is None:
            return None
        run.source_size_bytes = actual_size_bytes
        run.status = PipelineRunStatus.QUEUED.value
        run.stage = PipelineRunStage.QUEUED.value
        run.progress = 0
        run.status_message = "Видео загружено. Анализ скоро начнётся"
        run.upload_completed_at = datetime.now(timezone.utc)
        self.add_event(
            run.pipeline_runs_id,
            stage=PipelineRunStage.QUEUED,
            progress=0,
            message=run.status_message,
        )
        self._session.flush()
        return _run_to_dto(run)

    def add_artifact(
        self,
        *,
        run_id: str,
        artifact_type: PipelineArtifactType,
        object_key: str,
        content_type: str,
        size_bytes: int,
    ) -> PipelineArtifactDTO:
        artifact = PipelineArtifact(
            pipeline_runs_id=run_id,
            artifact_type=artifact_type.value,
            object_key=object_key,
            content_type=content_type,
            size_bytes=size_bytes,
        )
        self._session.add(artifact)
        self._session.flush()
        return _artifact_to_dto(artifact)

    def lock_assignment(self, assignment_id: str) -> bool:
        """Блокирует строку задания до конца транзакции. False — задания нет.

        Без этого два параллельных create_run, каждый насчитав MAX-1,
        оба вставят строку и лимит будет превышен.
        """
        assignment = self._session.exec(
            select(Assignment)
            .where(Assignment.assignments_id == assignment_id)
            .with_for_update()
        ).first()
        return assignment is not None

    def count_assignment_runs(self, assignment_id: str) -> int:
        total = self._session.exec(
            select(func.count(PipelineRun.pipeline_runs_id)).where(
                PipelineRun.assignments_id == assignment_id
            )
        ).one()
        return int(total)

    def add_event(
        self,
        run_id: str,
        *,
        stage: PipelineRunStage,
        progress: int,
        message: str | None,
    ) -> None:
        self._session.add(
            PipelineRunEvent(
                pipeline_runs_id=run_id,
                stage=_stage_value(stage),
                progress=progress,
                message=message,
            )
        )

    def claim_next(self, worker_id: str) -> PipelineRunDTO | None:
        statement = (
            select(PipelineRun)
            .where(PipelineRun.status == PipelineRunStatus.QUEUED.value)
            .order_by(PipelineRun.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        run = self._session.exec(statement).first()
        if run is None:
            self._session.rollback()
            return None

        run.status = PipelineRunStatus.PROCESSING.value
        run.stage = PipelineRunStage.PREPARING.value
        run.progress = 1
        run.status_message = "Готовим видео к анализу"
        run.worker_id = worker_id
        run.started_at = datetime.now(timezone.utc)
        self.add_event(
            run.pipeline_runs_id,
            stage=PipelineRunStage.PREPARING,
            progress=run.progress,
            message=run.status_message,
        )
        self._session.flush()
        return _run_to_dto(run)

    def update_progress(
        self,
        run_id: str,
        *,
        stage: PipelineRunStage,
        progress: int,
        message: str | None,
        create_event: bool = False,
    ) -> None:
        run = self._get_model(run_id, with_artifacts=False)
        if run is None:
            return
        run.stage = _stage_value(stage)
        run.progress = max(0, min(100, progress))
        run.status_message = message
        if create_event:
            self.add_event(
                run_id,
                stage=stage,
                progress=run.progress,
                message=message,
            )
        self._session.flush()

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
        run = self._get_model(run_id, with_artifacts=False)
        if run is None:
            return
        run.status = PipelineRunStatus.COMPLETED.value
        run.stage = PipelineRunStage.COMPLETED.value
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
            stage=PipelineRunStage.COMPLETED,
            progress=100,
            message=run.status_message,
        )
        self._session.flush()

    def mark_failed(
        self,
        run_id: str,
        *,
        error_code: str,
        error_message: str,
    ) -> None:
        run = self._get_model(run_id, with_artifacts=False)
        if run is None:
            return
        run.status = PipelineRunStatus.PROCESSING_FAILED.value
        run.stage = PipelineRunStage.FAILED.value
        run.status_message = "Анализ остановился с ошибкой"
        run.error_code = error_code
        run.error_message = error_message
        run.completed_at = datetime.now(timezone.utc)
        self.add_event(
            run_id,
            stage=PipelineRunStage.FAILED,
            progress=run.progress,
            message=run.status_message,
        )
        self._session.flush()

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()

    def _get_model(
        self,
        run_id: str,
        *,
        with_artifacts: bool = True,
        with_events: bool = False,
        with_refs: bool = False,
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
        if with_refs:
            statement = statement.options(
                selectinload(PipelineRun.assignment)
                .selectinload(Assignment.route)
                .defer(Route.geometry)
                .selectinload(Route.city)
                .defer(City.roads_geometry),
                selectinload(PipelineRun.operator),
            )
        else:
            statement = statement.options(
                noload(PipelineRun.assignment),
                noload(PipelineRun.operator),
            )
        return self._session.exec(statement).one_or_none()
