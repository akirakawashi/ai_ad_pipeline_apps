from __future__ import annotations

import logging
import mimetypes
import os
import shutil
import socket
import sys
import time
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from infrastructure.database.session import SessionFactory
from infrastructure.repositories.sql_pipeline_run_repository import (
    SqlPipelineRunRepository,
)
from infrastructure.storage.minio_storage import MinioStorage
from ml.pipeline.scripts.config import PipelineConfig
from ml.pipeline.scripts.runner import (
    PipelineModels,
    PipelineProgressReporter,
    load_pipeline_models,
    run_pipeline,
)
from settings.factory import ConfigFactory


logger = logging.getLogger("pipeline-worker")


def artifact_type(relative_path: Path) -> str:
    name = relative_path.name
    if relative_path.parts[:1] == ("crops",):
        return "crop"
    return {
        "input_meta.json": "input_metadata",
        "overlay.json": "overlay",
        "detections.csv": "detections",
        "tracks.csv": "tracks",
        "brand_summary_by_tracks.csv": "brand_summary",
        "brand_summary_by_detections.csv": "detection_summary",
        "frame_summary.csv": "frame_summary",
        "report.html": "report",
        "viewer.html": "viewer",
        "annotated_video.mp4": "annotated_video",
    }.get(name, "artifact")


class DatabaseProgressReporter(PipelineProgressReporter):
    def __init__(
        self,
        repository: SqlPipelineRunRepository,
        run_id: str,
    ) -> None:
        self._repository = repository
        self._run_id = run_id
        self._last_stage: str | None = None
        self._last_progress = -1

    def update(
        self,
        stage: str,
        progress: int,
        message: str | None = None,
    ) -> None:
        normalized = max(0, min(99, progress))
        create_event = (
            stage != self._last_stage
            or normalized - self._last_progress >= 10
        )
        self._repository.update_progress(
            self._run_id,
            stage=stage,
            progress=normalized,
            message=message,
            create_event=create_event,
        )
        self._last_stage = stage
        self._last_progress = normalized


class PipelineWorker:
    def __init__(self) -> None:
        self._config = ConfigFactory()
        self._storage = MinioStorage(self._config.object_storage)
        self._worker_id = f"{socket.gethostname()}:{os.getpid()}"
        self._models: PipelineModels | None = None

    def run_forever(self) -> None:
        self._storage.ensure_bucket()
        logger.info("worker started: %s", self._worker_id)
        while True:
            processed = self.process_next()
            if not processed:
                time.sleep(
                    self._config.pipeline.worker_poll_interval_sec
                )

    def process_next(self) -> bool:
        with SessionFactory() as session:
            repository = SqlPipelineRunRepository(session)
            run = repository.claim_next(self._worker_id)
            if run is None:
                return False

            run_root = (
                self._config.pipeline.worker_temp_dir / run.id
            ).resolve()
            input_path = run_root / "input" / run.source_name
            output_path = run_root / "output"
            reporter = DatabaseProgressReporter(repository, run.id)

            try:
                if run_root.exists():
                    shutil.rmtree(run_root)
                input_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.mkdir(parents=True, exist_ok=True)

                reporter.update(
                    "preparing",
                    1,
                    "Скачивание исходного видео",
                )
                self._storage.download_file(
                    run.source_object_key,
                    input_path,
                )

                pipeline_config = PipelineConfig(
                    input_path=input_path,
                    output_dir=output_path,
                    detector_model_path=(
                        self._config.pipeline.detector_model_path
                    ),
                    classifier_model_path=(
                        self._config.pipeline.classifier_model_path
                    ),
                    brand_overrides_path=(
                        self._config.pipeline.brand_overrides_path
                    ),
                    run_id=run.id,
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
                    "uploading_artifacts",
                    96,
                    "Загрузка результатов в MinIO",
                )
                self._upload_artifacts(
                    repository,
                    run.id,
                    output_path,
                )
                repository.mark_completed(
                    run.id,
                    fps=result.metadata.fps,
                    frame_count=result.metadata.frame_count,
                    frame_stride=result.metadata.frame_stride,
                    width=result.metadata.width,
                    height=result.metadata.height,
                )
                logger.info("run completed: %s", run.id)
            except Exception as exc:
                logger.exception("run failed: %s", run.id)
                repository.mark_failed(
                    run.id,
                    error_code=exc.__class__.__name__,
                    error_message=traceback.format_exc(),
                )
            finally:
                if run_root.exists():
                    shutil.rmtree(run_root)
        return True

    def _upload_artifacts(
        self,
        repository: SqlPipelineRunRepository,
        run_id: str,
        output_dir: Path,
    ) -> None:
        for source in sorted(
            path for path in output_dir.rglob("*") if path.is_file()
        ):
            relative = source.relative_to(output_dir)
            object_key = (
                f"runs/{run_id}/artifacts/{relative.as_posix()}"
            )
            content_type = (
                mimetypes.guess_type(source.name)[0]
                or "application/octet-stream"
            )
            self._storage.upload_file(
                source,
                object_key,
                content_type=content_type,
            )
            repository.add_artifact(
                run_id=run_id,
                artifact_type=artifact_type(relative),
                object_key=object_key,
                content_type=content_type,
                size_bytes=source.stat().st_size,
            )
        repository.commit()
def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    PipelineWorker().run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
