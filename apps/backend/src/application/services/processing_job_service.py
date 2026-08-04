from __future__ import annotations

from pathlib import PurePosixPath

from application.common.dto import (
    PipelineRunDTO,
    ProcessingArtifactInputDTO,
    ProcessingVideoMetadataDTO,
)
from application.exceptions import PipelineRunNotFoundError, ProcessingJobStateError
from application.interfaces import PipelineRunRepository, RunObjectStorage
from domain.entities import (
    PipelineRunStage,
    PipelineRunStatus,
    artifact_type_for_path,
    should_register_artifact,
)


class ProcessingJobService:
    """Граница между backend и отдельным сервисом обработки видео.

    Worker больше не получает доступ к PostgreSQL: backend сам атомарно
    захватывает очередь, принимает прогресс и одной транзакцией регистрирует
    готовые артефакты. Большие файлы при этом не идут через HTTP API — worker
    кладёт их прямо в MinIO и передаёт только манифест.
    """

    def __init__(
        self,
        repository: PipelineRunRepository,
        storage: RunObjectStorage,
    ) -> None:
        self._repository = repository
        self._storage = storage

    def claim_next(self) -> PipelineRunDTO | None:
        run = self._repository.claim_next()
        if run is not None:
            self._repository.commit()
        return run

    def report_progress(
        self,
        run_id: str,
        *,
        stage: PipelineRunStage,
        progress: int,
        message: str | None,
        create_event: bool,
    ) -> None:
        self._require_processing(run_id)
        self._repository.update_progress(
            run_id,
            stage=stage,
            progress=progress,
            message=message,
            create_event=create_event,
        )
        self._repository.commit()

    def complete(
        self,
        run_id: str,
        *,
        metadata: ProcessingVideoMetadataDTO,
        artifacts: list[ProcessingArtifactInputDTO],
    ) -> None:
        self._require_processing(run_id)
        seen_paths: set[str] = set()
        try:
            for artifact in artifacts:
                relative = self._relative_path(artifact.relative_path)
                relative_text = relative.as_posix()
                if relative_text in seen_paths:
                    raise ProcessingJobStateError(
                        f"Артефакт {relative_text} указан в манифесте дважды."
                    )
                seen_paths.add(relative_text)
                if not should_register_artifact(relative):
                    continue

                object_key = f"runs/{run_id}/artifacts/{relative_text}"
                actual_size = self._storage.stat(object_key).size
                if actual_size != artifact.size_bytes:
                    raise ProcessingJobStateError(
                        f"Размер артефакта {relative_text} не совпадает с хранилищем."
                    )
                self._repository.add_artifact(
                    run_id=run_id,
                    artifact_type=artifact_type_for_path(relative),
                    object_key=object_key,
                    content_type=artifact.content_type,
                    size_bytes=actual_size,
                )

            self._repository.mark_completed(
                run_id,
                fps=metadata.fps,
                frame_count=metadata.frame_count,
                frame_stride=metadata.frame_stride,
                width=metadata.width,
                height=metadata.height,
            )
            self._repository.commit()
        except Exception:
            self._repository.rollback()
            raise

    def fail(
        self,
        run_id: str,
        *,
        error_code: str,
        error_message: str,
    ) -> None:
        self._require_processing(run_id)
        self._repository.mark_failed(
            run_id,
            error_code=error_code,
            error_message=error_message,
        )
        self._repository.commit()

    def _require_processing(self, run_id: str) -> PipelineRunDTO:
        run = self._repository.get(
            run_id,
            with_artifacts=False,
            include_hidden=True,
        )
        if run is None:
            raise PipelineRunNotFoundError("Обработка не найдена.")
        if run.status != PipelineRunStatus.PROCESSING:
            raise ProcessingJobStateError(
                "Задача уже не находится в состоянии обработки."
            )
        return run

    @staticmethod
    def _relative_path(value: str) -> PurePosixPath:
        path = PurePosixPath(value)
        if not value or path.is_absolute() or ".." in path.parts or "." in path.parts:
            raise ProcessingJobStateError("Некорректный путь артефакта.")
        return path
