from __future__ import annotations

import io
import json
import re
import uuid
from pathlib import Path
from typing import Any

import pandas as pd

from application.services.run_serialization import (
    artifact_to_dict,
    run_to_dict,
)
from infrastructure.database.models import PipelineArtifactModel
from infrastructure.repositories.sql_pipeline_run_repository import (
    SqlPipelineRunRepository,
)
from infrastructure.storage.minio_storage import MinioStorage


ALLOWED_VIDEO_EXTENSIONS = {
    ".avi",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".webm",
}
class PipelineRunNotFoundError(LookupError):
    pass


class InvalidVideoError(ValueError):
    pass


def safe_file_name(value: str) -> str:
    name = Path(value).name
    stem = re.sub(r"[^a-zA-Z0-9_.-]+", "_", name).strip("_")
    return stem or "video.mp4"


class PipelineRunService:
    def __init__(
        self,
        repository: SqlPipelineRunRepository,
        storage: MinioStorage,
    ) -> None:
        self._repository = repository
        self._storage = storage

    def create_run(
        self,
        *,
        file_name: str,
        content_type: str | None,
        size_bytes: int,
    ) -> dict[str, Any]:
        safe_name = safe_file_name(file_name)
        if Path(safe_name).suffix.casefold() not in ALLOWED_VIDEO_EXTENSIONS:
            raise InvalidVideoError("Unsupported video extension")
        if size_bytes <= 0:
            raise InvalidVideoError("Video size must be greater than zero")

        run_id = str(uuid.uuid4())
        source_object_key = f"runs/{run_id}/source/{safe_name}"
        run = self._repository.create(
            run_id=run_id,
            source_name=safe_name,
            source_object_key=source_object_key,
            content_type=content_type or "application/octet-stream",
            size_bytes=size_bytes,
        )

        return {
            "run_id": run.id,
            "status": run.status,
            "upload": {
                "method": "PUT",
                "url": self._storage.presigned_put(run.source_object_key),
                "headers": {
                    "Content-Type": run.source_content_type
                    or "application/octet-stream"
                },
            },
        }

    def complete_upload(self, run_id: str) -> dict[str, Any]:
        run = self._require_run(run_id)
        if run.status not in {"uploading", "upload_failed"}:
            raise InvalidVideoError(
                f"Upload cannot be completed from status {run.status}"
            )
        object_stat = self._storage.stat(run.source_object_key)
        self._repository.add_artifact(
            run_id=run.id,
            artifact_type="source_video",
            object_key=run.source_object_key,
            content_type=run.source_content_type
            or "application/octet-stream",
            size_bytes=object_stat.size,
        )
        self._repository.mark_upload_complete(
            run,
            actual_size_bytes=object_stat.size,
        )
        return run_to_dict(run)

    def list_runs(
        self,
        *,
        page: int,
        page_size: int,
        status: str | None,
    ) -> dict[str, Any]:
        runs, total = self._repository.list_runs(
            page=page,
            page_size=page_size,
            status=status,
        )
        return {
            "items": [
                run_to_dict(run, include_artifacts=True) for run in runs
            ],
            "page": page,
            "page_size": page_size,
            "total": total,
        }

    def get_run(self, run_id: str) -> dict[str, Any]:
        run = self._require_run(run_id, with_events=True)
        return run_to_dict(
            run,
            include_artifacts=True,
            include_events=True,
        )

    def get_artifacts(self, run_id: str) -> list[dict[str, Any]]:
        run = self._require_run(run_id)
        return [artifact_to_dict(artifact) for artifact in run.artifacts]

    def get_artifact_url(
        self,
        run_id: str,
        artifact_id: str,
    ) -> dict[str, Any]:
        run = self._require_run(run_id)
        artifact = next(
            (
                item
                for item in run.artifacts
                if item.id == artifact_id
            ),
            None,
        )
        if artifact is None:
            raise PipelineRunNotFoundError(
                f"Artifact {artifact_id} was not found"
            )
        return {
            "artifact_id": artifact.id,
            "url": self._storage.presigned_get(artifact.object_key),
        }

    def get_playback(self, run_id: str) -> dict[str, Any]:
        run = self._require_run(run_id)
        by_type = {item.artifact_type: item for item in run.artifacts}
        source = by_type.get("source_video")
        annotated = by_type.get("annotated_video")
        return {
            "source_url": (
                self._storage.presigned_get(source.object_key)
                if source
                else None
            ),
            "annotated_url": (
                self._storage.presigned_get(annotated.object_key)
                if annotated
                else None
            ),
        }

    def get_overlay(self, run_id: str) -> dict[str, Any]:
        artifact = self._require_artifact(run_id, "overlay")
        return json.loads(self._storage.read_text(artifact.object_key))

    def get_summary(self, run_id: str) -> dict[str, Any]:
        run = self._require_run(run_id)
        artifact = self._find_artifact(run.artifacts, "brand_summary")
        brands: list[dict[str, Any]] = []
        if artifact:
            dataframe = self._read_csv(artifact)
            if not dataframe.empty:
                brands = self._native_rows(dataframe)

        total_objects = sum(int(row.get("object_count", 0)) for row in brands)
        total_visibility = sum(
            float(row.get("video_visibility_weighted_seconds", 0.0))
            for row in brands
        )
        return {
            "run": run_to_dict(run, include_artifacts=True),
            "totals": {
                "total_objects": total_objects,
                "visibility_index": total_visibility,
            },
            "brands": brands,
        }

    def get_objects(
        self,
        run_id: str,
        *,
        limit: int | None,
    ) -> dict[str, Any]:
        run = self._require_run(run_id)
        artifact = self._find_artifact(run.artifacts, "tracks")
        if artifact is None:
            return {"run_id": run_id, "objects": []}
        dataframe = self._read_csv(artifact)
        if dataframe.empty:
            return {"run_id": run_id, "objects": []}
        if "business_visible" in dataframe.columns:
            visible = pd.to_numeric(
                dataframe["business_visible"],
                errors="coerce",
            ).fillna(0)
            dataframe = dataframe.loc[visible > 0]
        dataframe = dataframe.sort_values(
            "video_visibility_weighted_seconds",
            ascending=False,
        )
        if limit:
            dataframe = dataframe.head(limit)
        rows = self._native_rows(dataframe)
        for row in rows:
            crop_path = str(row.get("best_crop_path") or "")
            crop_name = Path(crop_path).name
            crop_artifact = next(
                (
                    item
                    for item in run.artifacts
                    if item.artifact_type == "crop"
                    and item.object_key.endswith(f"/{crop_name}")
                ),
                None,
            )
            row["crop_url"] = (
                self._storage.presigned_get(crop_artifact.object_key)
                if crop_artifact
                else None
            )
        return {"run_id": run_id, "objects": rows}

    def get_timeline(
        self,
        run_id: str,
        *,
        bucket_seconds: int,
    ) -> dict[str, Any]:
        run = self._require_run(run_id)
        artifact = self._find_artifact(run.artifacts, "detections")
        if artifact is None:
            return {
                "run_id": run_id,
                "bucket_seconds": bucket_seconds,
                "points": [],
            }
        dataframe = self._read_csv(artifact)
        if dataframe.empty:
            points = []
        else:
            if "business_visible" in dataframe.columns:
                visible = pd.to_numeric(
                    dataframe["business_visible"],
                    errors="coerce",
                ).fillna(0)
                dataframe = dataframe.loc[visible > 0].copy()
            dataframe["bucket_start_sec"] = (
                pd.to_numeric(
                    dataframe["timestamp_sec"],
                    errors="coerce",
                ).fillna(0)
                // bucket_seconds
                * bucket_seconds
            )
            grouped = (
                dataframe.groupby(
                    ["bucket_start_sec", "business_brand"],
                    dropna=False,
                )
                .agg(
                    detection_count=("det_index", "count"),
                    visibility_score=("video_visibility_score", "sum"),
                )
                .reset_index()
            )
            points = self._native_rows(grouped)
        return {
            "run_id": run_id,
            "bucket_seconds": bucket_seconds,
            "points": points,
        }

    def _require_run(
        self,
        run_id: str,
        *,
        with_events: bool = False,
    ):
        run = self._repository.get(run_id, with_events=with_events)
        if run is None:
            raise PipelineRunNotFoundError(
                f"Pipeline run {run_id} was not found"
            )
        return run

    def _require_artifact(
        self,
        run_id: str,
        artifact_type: str,
    ) -> PipelineArtifactModel:
        run = self._require_run(run_id)
        artifact = self._find_artifact(run.artifacts, artifact_type)
        if artifact is None:
            raise PipelineRunNotFoundError(
                f"Artifact {artifact_type} was not found"
            )
        return artifact

    @staticmethod
    def _find_artifact(
        artifacts: list[PipelineArtifactModel],
        artifact_type: str,
    ) -> PipelineArtifactModel | None:
        return next(
            (
                artifact
                for artifact in artifacts
                if artifact.artifact_type == artifact_type
            ),
            None,
        )

    def _read_csv(self, artifact: PipelineArtifactModel) -> pd.DataFrame:
        value = self._storage.read_bytes(artifact.object_key)
        if not value:
            return pd.DataFrame()
        return pd.read_csv(io.BytesIO(value))

    @staticmethod
    def _native_rows(dataframe: pd.DataFrame) -> list[dict[str, Any]]:
        return json.loads(
            dataframe.to_json(orient="records", force_ascii=False)
        )
