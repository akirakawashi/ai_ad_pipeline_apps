from __future__ import annotations

import logging
import mimetypes
import os
import shutil
import socket
import time
import traceback
from pathlib import Path

from ml.pipeline.scripts.config import PipelineConfig
from ml.pipeline.scripts.runner import (
    PipelineModels,
    load_pipeline_models,
    run_pipeline,
)

from application.interfaces import PipelineRunRepository, WorkerObjectStorage
from domain.entities import (
    PipelineRunStage,
    artifact_type_for_path,
    should_register_artifact,
)
from infrastructure.database.session import create_session
from infrastructure.repositories.sql_pipeline_run_repository import (
    SqlPipelineRunRepository,
)
from infrastructure.storage.minio_storage import MinioStorage
from settings.factory import get_settings
from worker.progress import DatabaseProgressReporter

logger = logging.getLogger("pipeline-worker")


class PipelineWorker:
    def __init__(self) -> None:
        self._config = get_settings()
        self._storage: WorkerObjectStorage = MinioStorage(self._config.object_storage)
        self._worker_id = f"{socket.gethostname()}:{os.getpid()}"
        self._models: PipelineModels | None = None

    def run_forever(self) -> None:
        self._storage.ensure_bucket()
        logger.info("worker started: %s", self._worker_id)
        while True:
            processed = self.process_next()
            if not processed:
                time.sleep(self._config.pipeline.worker_poll_interval_sec)

    def process_next(self) -> bool:
        with create_session() as session:
            repository = SqlPipelineRunRepository(session)
            run = repository.claim_next(self._worker_id)
            if run is None:
                return False
            repository.commit()

            run_root = (
                self._config.pipeline.worker_temp_dir / run.run_id
            ).resolve()
            input_path = run_root / "input" / run.source_name
            output_path = run_root / "output"
            reporter = DatabaseProgressReporter(
                repository,
                run.run_id,
            )

            try:
                if run_root.exists():
                    shutil.rmtree(run_root)
                input_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.mkdir(parents=True, exist_ok=True)

                reporter.update(
                    PipelineRunStage.PREPARING,
                    1,
                    "Загружаем исходное видео для анализа",
                )
                self._storage.download_file(
                    run.source_object_key,
                    input_path,
                )

                pipeline_config = PipelineConfig(
                    input_path=input_path,
                    output_dir=output_path,
                    detector_model_path=self._config.pipeline.detector_model_path,
                    classifier_model_path=(self._config.pipeline.classifier_model_path),
                    brand_overrides_path=self._config.pipeline.brand_overrides_path,
                    run_id=run.run_id,
                    frame_stride=self._config.pipeline.frame_stride,
                    device=self._config.pipeline.device,
                )
                if self._models is None:
                    self._models = load_pipeline_models(
                        pipeline_config,
                        include_classifier=True,
                    )

                result = run_pipeline(
                    pipeline_config,
                    models=self._models,
                    progress_reporter=reporter,
                )

                reporter.update(
                    PipelineRunStage.UPLOADING_ARTIFACTS,
                    96,
                    "Сохраняем результаты анализа",
                )
                self._upload_artifacts(
                    repository,
                    run.run_id,
                    output_path,
                )
                repository.mark_completed(
                    run.run_id,
                    fps=result.metadata.fps,
                    frame_count=result.metadata.frame_count,
                    frame_stride=result.metadata.frame_stride,
                    width=result.metadata.width,
                    height=result.metadata.height,
                )
                repository.commit()
                logger.info(
                    "run completed: %s",
                    run.run_id,
                )
            except Exception as exc:
                logger.exception(
                    "run failed: %s",
                    run.run_id,
                )
                repository.rollback()
                repository.mark_failed(
                    run.run_id,
                    error_code=exc.__class__.__name__,
                    error_message=traceback.format_exc(),
                )
                repository.commit()
            finally:
                if run_root.exists():
                    shutil.rmtree(run_root)
        return True

    def _upload_artifacts(
        self,
        repository: PipelineRunRepository,
        run_id: str,
        output_dir: Path,
    ) -> None:
        for source in sorted(path for path in output_dir.rglob("*") if path.is_file()):
            relative = source.relative_to(output_dir)
            object_key = f"runs/{run_id}/artifacts/{relative.as_posix()}"
            content_type = (
                mimetypes.guess_type(source.name)[0] or "application/octet-stream"
            )
            self._storage.upload_file(
                source,
                object_key,
                content_type=content_type,
            )
            if not should_register_artifact(relative):
                continue
            repository.add_artifact(
                run_id=run_id,
                artifact_type=artifact_type_for_path(relative),
                object_key=object_key,
                content_type=content_type,
                size_bytes=source.stat().st_size,
            )
        repository.commit()
