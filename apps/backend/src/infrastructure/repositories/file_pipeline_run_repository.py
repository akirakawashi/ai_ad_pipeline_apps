from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any

import pandas as pd

from application.common.dto.pipeline_run import (
    PipelineRunDTO,
    RunArtifactDTO,
    RunObjectsDTO,
    RunSummaryDTO,
    RunTimelineDTO,
)
from application.interfaces.pipeline_run_repository import PipelineRunRepository
from domain.entities.pipeline_run import PipelineRun, RunArtifact
from domain.exceptions.pipeline_run import (
    InvalidPipelineArtifactPathError,
    PipelineArtifactNotFoundError,
    PipelineRunDataError,
    PipelineRunNotFoundError,
)


BRAND_LABELS = {
    "mts": "МТС",
    "miranda": "Миранда",
    "plus7": "+7",
    "other": "Другая реклама",
}
BRAND_ORDER = ["mts", "miranda", "plus7", "other"]
TARGET_BRANDS = {"mts", "miranda", "plus7"}


class FilePipelineRunRepository(PipelineRunRepository):
    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir.resolve()

    def list_runs(self) -> list[PipelineRun]:
        if not self._output_dir.exists():
            return []
        runs = [
            self._build_run(item)
            for item in self._output_dir.iterdir()
            if item.is_dir() and not item.name.startswith(".")
        ]
        return sorted(runs, key=lambda item: item.created_at, reverse=True)

    def get_run(self, run_id: str) -> PipelineRun:
        run_dir = self._run_dir(run_id)
        if not run_dir.exists() or not run_dir.is_dir():
            raise PipelineRunNotFoundError(run_id)
        return self._build_run(run_dir)

    def list_artifacts(self, run_id: str) -> list[RunArtifact]:
        run_dir = self._existing_run_dir(run_id)
        candidates = [
            run_dir / "viewer.html",
            run_dir / "report.html",
            run_dir / "overlay.json",
            run_dir / "video" / "annotated_video.mp4",
            run_dir / "brand_summary_by_tracks.csv",
            run_dir / "tracks.csv",
            run_dir / "detections.csv",
        ]
        charts_dir = run_dir / "charts"
        if charts_dir.exists():
            candidates.extend(sorted(charts_dir.iterdir()))

        artifacts = []
        for path in candidates:
            if path.is_file():
                artifacts.append(self._artifact_from_path(run_dir, path))
        return artifacts

    def get_artifact_path(self, run_id: str, relative_path: str) -> Path:
        run_dir = self._existing_run_dir(run_id)
        if not relative_path or relative_path.startswith("/"):
            raise InvalidPipelineArtifactPathError(relative_path)
        path = (run_dir / relative_path).resolve()
        if not path.is_relative_to(run_dir):
            raise InvalidPipelineArtifactPathError(relative_path)
        if not path.is_file():
            raise PipelineArtifactNotFoundError(run_id, relative_path)
        return path

    def get_summary(self, run_id: str) -> RunSummaryDTO:
        run = self.get_run(run_id)
        tracks_df = self._read_csv(run_id, "brand_summary_by_tracks.csv")
        brands = self._brand_summary(tracks_df)
        totals = self._totals(brands)
        return RunSummaryDTO(
            run=self._run_to_dto(run),
            totals=totals,
            brands=brands,
            artifacts=[self._artifact_to_dto(artifact) for artifact in self.list_artifacts(run_id)],
        )

    def get_objects(self, run_id: str, limit: int | None = None) -> RunObjectsDTO:
        tracks_df = self._read_csv(run_id, "tracks.csv")
        visible_tracks_df = filter_business_visible(tracks_df)
        if visible_tracks_df.empty:
            return RunObjectsDTO(run_id=run_id, objects=[])

        object_frame = build_object_frame(visible_tracks_df, self._existing_run_dir(run_id))
        object_frame = object_frame.sort_values("visibility_index", ascending=False)
        if limit is not None:
            object_frame = object_frame.head(limit)
        return RunObjectsDTO(
            run_id=run_id,
            objects=[to_native_dict(row) for row in object_frame.to_dict("records")],
        )

    def get_timeline(self, run_id: str, bucket_seconds: int) -> RunTimelineDTO:
        bucket_seconds = max(1, min(bucket_seconds, 300))
        detections_df = self._read_csv(run_id, "detections.csv")
        visible_detections_df = filter_business_visible(detections_df)
        points = build_timeline_points(visible_detections_df, bucket_seconds)
        return RunTimelineDTO(run_id=run_id, bucket_seconds=bucket_seconds, points=points)

    def get_overlay(self, run_id: str) -> dict[str, Any]:
        run_dir = self._existing_run_dir(run_id)
        overlay_path = run_dir / "overlay.json"
        if not overlay_path.is_file():
            raise PipelineArtifactNotFoundError(run_id, "overlay.json")
        try:
            return json.loads(overlay_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise PipelineRunDataError(run_id, f"overlay.json is not valid JSON: {exc}") from exc

    def _run_dir(self, run_id: str) -> Path:
        if "/" in run_id or "\\" in run_id or run_id in {"", ".", ".."}:
            raise PipelineRunNotFoundError(run_id)
        return (self._output_dir / run_id).resolve()

    def _existing_run_dir(self, run_id: str) -> Path:
        run_dir = self._run_dir(run_id)
        if not run_dir.exists() or not run_dir.is_dir() or not run_dir.is_relative_to(self._output_dir):
            raise PipelineRunNotFoundError(run_id)
        return run_dir

    def _build_run(self, run_dir: Path) -> PipelineRun:
        metadata = self._read_metadata(run_dir)
        fps = optional_float(metadata.get("fps"))
        frame_count = optional_int(metadata.get("frame_count"))
        duration_sec = frame_count / fps if fps and frame_count else None
        source_path = optional_str(metadata.get("source_path"))
        return PipelineRun(
            run_id=run_dir.name,
            path=run_dir,
            source_path=source_path,
            source_name=Path(source_path).name if source_path else None,
            input_type=optional_str(metadata.get("input_type")),
            fps=fps,
            frame_count=frame_count,
            frame_stride=optional_int(metadata.get("frame_stride")),
            duration_sec=duration_sec,
            width=optional_int(metadata.get("width")),
            height=optional_int(metadata.get("height")),
            created_at=run_dir.stat().st_mtime,
            has_overlay=(run_dir / "overlay.json").is_file(),
            has_viewer=(run_dir / "viewer.html").is_file(),
            has_report=(run_dir / "report.html").is_file(),
            has_annotated_video=(run_dir / "video" / "annotated_video.mp4").is_file(),
        )

    def _read_metadata(self, run_dir: Path) -> dict[str, Any]:
        path = run_dir / "input_meta.json"
        if not path.is_file():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _read_csv(self, run_id: str, name: str) -> pd.DataFrame:
        path = self._existing_run_dir(run_id) / name
        if not path.is_file():
            return pd.DataFrame()
        return pd.read_csv(path)

    def _brand_summary(self, dataframe: pd.DataFrame) -> list[dict[str, Any]]:
        if dataframe.empty:
            return []
        required = {"brand", "object_count", "video_visibility_weighted_seconds"}
        if not required.issubset(dataframe.columns):
            return []

        summary = dataframe.copy()
        summary["brand"] = normalize_brand_series(summary["brand"])
        summary["brand_label"] = summary["brand"].map(brand_label)
        summary["brand_order"] = summary["brand"].map(brand_order)
        summary["visibility_index"] = pd.to_numeric(
            summary["video_visibility_weighted_seconds"],
            errors="coerce",
        ).fillna(0.0)
        summary["object_count"] = pd.to_numeric(summary["object_count"], errors="coerce").fillna(0).astype(int)
        summary["visibility_share"] = share(summary["visibility_index"])
        summary = summary.sort_values(["brand_order", "brand_label"])

        columns = [
            "brand",
            "brand_label",
            "object_count",
            "visibility_index",
            "visibility_share",
            "mean_final_brand_conf",
            "max_final_brand_conf",
            "first_timestamp_sec",
            "last_timestamp_sec",
        ]
        existing_columns = [column for column in columns if column in summary.columns]
        return [to_native_dict(row) for row in summary[existing_columns].to_dict("records")]

    def _totals(self, brands: list[dict[str, Any]]) -> dict[str, Any]:
        total_objects = sum(int(item.get("object_count", 0)) for item in brands)
        total_visibility = sum(float(item.get("visibility_index", 0.0)) for item in brands)
        target_objects = sum(int(item.get("object_count", 0)) for item in brands if item.get("brand") in TARGET_BRANDS)
        target_visibility = sum(
            float(item.get("visibility_index", 0.0)) for item in brands if item.get("brand") in TARGET_BRANDS
        )
        return {
            "total_objects": total_objects,
            "target_objects": target_objects,
            "other_objects": total_objects - target_objects,
            "visibility_index": total_visibility,
            "target_visibility_index": target_visibility,
            "other_visibility_index": total_visibility - target_visibility,
            "target_visibility_share": target_visibility / total_visibility if total_visibility else 0.0,
        }

    def _artifact_from_path(self, run_dir: Path, path: Path) -> RunArtifact:
        relative_path = path.relative_to(run_dir).as_posix()
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return RunArtifact(
            name=path.name,
            relative_path=relative_path,
            media_type=media_type,
            size_bytes=path.stat().st_size,
        )

    def _artifact_to_dto(self, artifact: RunArtifact) -> RunArtifactDTO:
        return RunArtifactDTO(
            name=artifact.name,
            relative_path=artifact.relative_path,
            media_type=artifact.media_type,
            size_bytes=artifact.size_bytes,
        )

    def _run_to_dto(self, run: PipelineRun) -> PipelineRunDTO:
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


def filter_business_visible(dataframe: pd.DataFrame) -> pd.DataFrame:
    if dataframe.empty or "business_visible" not in dataframe.columns:
        return dataframe.iloc[0:0].copy()
    visible = pd.to_numeric(dataframe["business_visible"], errors="coerce").fillna(0).astype(int) == 1
    return dataframe[visible].copy()


def build_object_frame(tracks_df: pd.DataFrame, run_dir: Path) -> pd.DataFrame:
    best_crops = (
        tracks_df.sort_values("video_visibility_weighted_seconds", ascending=False)
        .drop_duplicates(["object_id"])
        .loc[:, ["object_id", "best_crop_path", "best_frame_index", "best_timestamp_sec", "final_status_reason"]]
    )
    grouped = (
        tracks_df.groupby(["object_id", "business_brand"], dropna=False)
        .agg(
            track_fragment_count=("track_id", "count"),
            detections_count=("detections_count", "sum"),
            first_timestamp_sec=("first_timestamp_sec", "min"),
            last_timestamp_sec=("last_timestamp_sec", "max"),
            visible_duration_sec=("visible_duration_sec", "sum"),
            visibility_index=("video_visibility_weighted_seconds", "sum"),
            max_area_ratio=("max_area_ratio", "max"),
            mean_brand_conf=("final_brand_conf", "mean"),
            max_brand_conf=("final_brand_conf", "max"),
            mean_score=("track_final_score", "mean"),
        )
        .reset_index()
        .rename(columns={"business_brand": "brand"})
    )
    grouped = grouped.merge(best_crops, on="object_id", how="left")
    grouped["brand"] = normalize_brand_series(grouped["brand"])
    grouped["brand_label"] = grouped["brand"].map(brand_label)
    grouped["best_crop_artifact_path"] = grouped["best_crop_path"].map(
        lambda value: artifact_path_from_absolute(value, run_dir)
    )
    return grouped


def build_timeline_points(detections_df: pd.DataFrame, bucket_seconds: int) -> list[dict[str, Any]]:
    required_columns = {"timestamp_sec", "object_id", "business_brand", "video_visibility_score"}
    if detections_df.empty or not required_columns.issubset(detections_df.columns):
        return []

    dataframe = detections_df.copy()
    dataframe["brand"] = normalize_brand_series(dataframe["business_brand"])
    dataframe["timestamp_sec"] = pd.to_numeric(dataframe["timestamp_sec"], errors="coerce")
    dataframe["video_visibility_score"] = pd.to_numeric(dataframe["video_visibility_score"], errors="coerce")
    dataframe = dataframe.dropna(subset=["timestamp_sec", "video_visibility_score", "object_id"])
    if dataframe.empty:
        return []

    dataframe["time_bucket_sec"] = (dataframe["timestamp_sec"] // bucket_seconds).astype(int) * bucket_seconds
    object_bucket = (
        dataframe.groupby(["time_bucket_sec", "object_id", "brand"], as_index=False)
        .agg(visibility_index=("video_visibility_score", "max"))
    )
    timeline = (
        object_bucket.groupby(["time_bucket_sec", "brand"], as_index=False)
        .agg(
            visibility_index=("visibility_index", "sum"),
            object_count=("object_id", "nunique"),
        )
    )
    timeline = complete_timeline_buckets(timeline, bucket_seconds)
    timeline["brand_label"] = timeline["brand"].map(brand_label)
    timeline["time_label"] = timeline["time_bucket_sec"].map(format_time)
    return [to_native_dict(row) for row in timeline.to_dict("records")]


def complete_timeline_buckets(timeline: pd.DataFrame, bucket_seconds: int) -> pd.DataFrame:
    minimum = int(timeline["time_bucket_sec"].min())
    maximum = int(timeline["time_bucket_sec"].max())
    brands = [brand for brand in BRAND_ORDER if brand in set(timeline["brand"])]
    index = pd.MultiIndex.from_product(
        [range(minimum, maximum + bucket_seconds, bucket_seconds), brands],
        names=["time_bucket_sec", "brand"],
    )
    return (
        timeline.set_index(["time_bucket_sec", "brand"])
        .reindex(index, fill_value=0.0)
        .reset_index()
    )


def normalize_brand_series(series: pd.Series) -> pd.Series:
    return series.fillna("other").replace({"": "other"}).astype(str)


def brand_label(brand: str) -> str:
    return BRAND_LABELS.get(brand, brand)


def brand_order(brand: str) -> int:
    try:
        return BRAND_ORDER.index(brand)
    except ValueError:
        return len(BRAND_ORDER)


def share(series: pd.Series) -> pd.Series:
    total = float(series.sum())
    if not total:
        return series * 0.0
    return series / total


def artifact_path_from_absolute(value: Any, run_dir: Path) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        return value
    try:
        return path.resolve().relative_to(run_dir).as_posix()
    except ValueError:
        return None


def optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def optional_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result


def optional_int(value: Any) -> int | None:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result


def format_time(seconds: Any) -> str:
    total = max(0, int(float(seconds)))
    minutes = total // 60
    rest = total % 60
    return f"{minutes:02d}:{rest:02d}"


def to_native_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {key: to_native_value(value) for key, value in row.items()}


def to_native_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value

