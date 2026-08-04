from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import noload, selectinload
from sqlmodel import Session, select

from application.common.dto import (
    PipelineArtifactDTO,
    PipelineRunDTO,
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


def _shot_finished_at(run: PipelineRun) -> datetime | None:
    """Конец съёмки не хранится: старт плюс длительность самого видео.

    Так поле физически не может разойтись с файлом. Пока видео не обработано,
    длительность неизвестна — возвращаем None, интерфейс покажет прочерк.
    """
    if not run.duration_sec:
        return None
    return run.shot_started_at + timedelta(seconds=run.duration_sec)


def _run_to_dto(run: PipelineRun, *, with_refs: bool = False) -> PipelineRunDTO:
    # with_refs=True только там, где связи загружены через selectinload.
    # Воркер зовёт эту функцию на detached-инстансах — там assignment
    # и uploaded_by трогать нельзя.
    return PipelineRunDTO(
        assignment=assignment_ref(run) if with_refs else None,
        uploaded_by=user_ref(run.uploaded_by) if with_refs else None,
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
        assignment_id: str,
        shot_started_at: datetime,
        uploaded_by_user_id: str | None = None,
    ) -> PipelineRunDTO:
        run = PipelineRun(
            pipeline_runs_id=run_id,
            source_name=source_name,
            source_object_key=source_object_key,
            source_content_type=content_type,
            source_size_bytes=size_bytes,
            assignments_id=assignment_id,
            shot_started_at=shot_started_at,
            uploaded_by_users_id=uploaded_by_user_id,
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
    ) -> tuple[list[PipelineRunDTO], int]:
        filters = []
        if status:
            filters.append(PipelineRun.status == _status_value(status))
        if assignment_id:
            filters.append(PipelineRun.assignments_id == assignment_id)

        # Маршрут и город достаём подзапросом по цепочке assignment → route → city,
        # чтобы не денормализовать их в pipeline_runs. Скрытые задания отсекаются
        # тем же подзапросом, и безусловно: съёмка спрятанной кампании не должна
        # остаться в общем списке — карточка вела бы на страницу, дающую 404.
        assignment_ids = select(Assignment.assignments_id).where(
            Assignment.is_active.is_(True)
        )
        if route_id or city_id:
            assignment_ids = assignment_ids.join(
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
        include_hidden: bool = False,
    ) -> PipelineRunDTO | None:
        """Съёмка для показа. None — нет её или скрыто задание, в которое она сдана.

        Единственная точка чтения съёмки продуктом: через неё идут и карточка,
        и сводка, и объекты, и таймлайн, и плеер, — поэтому скрытие проверяется
        здесь одной строкой, а не в семи местах.

        `include_hidden` нужен ровно одному вызову — завершению загрузки. Между
        созданием съёмки и «файл долит» проходят минуты, и если в эту щель
        задание спрятали, отказ оставил бы строку навсегда в статусе `uploading`
        и брошенный объект в MinIO. Дозагрузить начатое — запись, а пути записи
        скрытия не знают: по ним же ходит воркер.
        """
        run = self._get_model(
            run_id,
            with_artifacts=with_artifacts,
            with_refs=True,
        )
        if run is None:
            return None
        if not include_hidden and (
            run.assignment is None or not run.assignment.is_active
        ):
            return None
        return _run_to_dto(run, with_refs=True)

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
        """Блокирует строку задания. False, если задания нет или оно скрыто.

        Блокировка — против гонки: без неё два параллельных create_run, каждый
        насчитав MAX-1, оба вставят строку и лимит будет превышен.

        Скрытое здесь неотличимо от несуществующего намеренно: в выпадашке его
        уже нет, но идентификатор живёт в адресе страницы загрузки — открытая со
        вчера вкладка иначе долила бы видео в спрятанную кампанию.

        Это проверка **начала** загрузки, и только его. Завершение
        (`complete_upload`) скрытое задание пропускает: файл к тому моменту уже
        в хранилище, и отказ оставил бы строку висеть в `uploading` рядом с
        осиротевшим объектом.
        """
        assignment = self._session.exec(
            select(Assignment)
            .where(Assignment.assignments_id == assignment_id)
            .with_for_update()
        ).first()
        return assignment is not None and assignment.is_active

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

    def claim_next(self) -> PipelineRunDTO | None:
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
        with_refs: bool = False,
    ) -> PipelineRun | None:
        statement = select(PipelineRun).where(PipelineRun.pipeline_runs_id == run_id)
        if with_artifacts:
            statement = statement.options(selectinload(PipelineRun.artifacts))
        else:
            statement = statement.options(noload(PipelineRun.artifacts))
        if with_refs:
            statement = statement.options(
                selectinload(PipelineRun.assignment)
                .selectinload(Assignment.route)
                .defer(Route.geometry)
                .selectinload(Route.city)
                .defer(City.roads_geometry),
                selectinload(PipelineRun.uploaded_by),
            )
        else:
            statement = statement.options(
                noload(PipelineRun.assignment),
                noload(PipelineRun.uploaded_by),
            )
        return self._session.exec(statement).one_or_none()
