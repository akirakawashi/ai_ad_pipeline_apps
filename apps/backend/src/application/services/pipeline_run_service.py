from __future__ import annotations

import io
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

import pandas as pd
from pandas.errors import EmptyDataError
from pydantic import BaseModel

from application.common.dto import (
    BrandSummaryDTO,
    CreateRunDTO,
    OverlayPayloadDTO,
    PaginatedRunsDTO,
    PipelineArtifactDTO,
    PipelineRunDTO,
    PlaybackDTO,
    RunObjectDTO,
    RunObjectsDTO,
    RunSummaryDTO,
    RunSummaryTotalsDTO,
    RunTimelineDTO,
    RunTimelinePointDTO,
    UploadTargetDTO,
)
from application.exceptions import (
    CatalogNotFoundError,
    InvalidVideoError,
    AssignmentFullError,
    PipelineRunNotFoundError,
)
from application.interfaces import PipelineRunRepository, RunObjectStorage
from domain.entities import PipelineArtifactType, PipelineRunStatus
from domain.geozones import GeozoneInterval, beta

ALLOWED_VIDEO_EXTENSIONS = {
    ".avi",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".webm",
}

# Ограничение продукта, а не схемы: поднять — правка одной строки, без миграции.
MAX_ASSIGNMENT_SHOOTINGS = 20

ModelT = TypeVar("ModelT", bound=BaseModel)


def safe_file_name(value: str) -> str:
    name = Path(value).name
    stem = re.sub(r"[^a-zA-Z0-9_.-]+", "_", name).strip("_")
    return stem or "video.mp4"


def crop_object_key(run_id: str, crop_path: str) -> str | None:
    if not crop_path:
        return None

    path_parts = [part for part in crop_path.replace("\\", "/").split("/") if part]
    try:
        crops_index = path_parts.index("crops")
    except ValueError:
        return None

    crop_relative_path = "/".join(path_parts[crops_index:])
    if not crop_relative_path:
        return None

    return f"runs/{run_id}/artifacts/{crop_relative_path}"


class PipelineRunService:
    def __init__(
        self,
        repository: PipelineRunRepository,
        storage: RunObjectStorage,
    ) -> None:
        self._repository = repository
        self._storage = storage

    def create_run(
        self,
        *,
        file_name: str,
        content_type: str | None,
        size_bytes: int,
        assignment_id: str,
        shot_started_at: datetime,
        operator_user_id: str | None = None,
    ) -> CreateRunDTO:
        safe_name = safe_file_name(file_name)
        if Path(safe_name).suffix.casefold() not in ALLOWED_VIDEO_EXTENSIONS:
            raise InvalidVideoError(
                "Этот формат видео не поддерживается. Загрузите MP4, MOV, MKV или WebM."
            )
        if size_bytes <= 0:
            raise InvalidVideoError("Файл пустой. Выберите другое видео.")

        # Задание обязательно, поэтому проверки безусловны. Блокировка строки
        # задания сериализует параллельные create_run: иначе два запроса, каждый
        # насчитав MAX-1, оба вставят.
        if not self._repository.lock_assignment(assignment_id):
            self._repository.rollback()
            raise CatalogNotFoundError("Задание не найдено.")
        if self._repository.count_assignment_runs(assignment_id) >= MAX_ASSIGNMENT_SHOOTINGS:
            self._repository.rollback()
            raise AssignmentFullError(
                f"В задание можно загрузить не более {MAX_ASSIGNMENT_SHOOTINGS} видео."
            )

        run_id = str(uuid.uuid4())
        source_object_key = f"runs/{run_id}/source/{safe_name}"
        run = self._repository.create(
            run_id=run_id,
            source_name=safe_name,
            source_object_key=source_object_key,
            content_type=content_type or "application/octet-stream",
            size_bytes=size_bytes,
            assignment_id=assignment_id,
            shot_started_at=shot_started_at,
            operator_user_id=operator_user_id,
        )
        self._repository.commit()

        return CreateRunDTO(
            run_id=run.run_id,
            status=run.status,
            upload=UploadTargetDTO(
                method="PUT",
                url=self._storage.presigned_put(run.source_object_key),
                headers={
                    "Content-Type": run.source_content_type
                    or "application/octet-stream"
                },
            ),
        )

    def complete_upload(self, run_id: str) -> PipelineRunDTO:
        # include_hidden: файл уже в хранилище. Если задание спрятали, пока шла
        # заливка, отказать здесь — значит оставить строку в `uploading` и
        # брошенный объект в MinIO. Довести начатое до конца дешевле; видно
        # съёмку всё равно не будет, пока задание не вернут.
        run = self._require_run(run_id, with_artifacts=False, include_hidden=True)
        if run.status not in {
            PipelineRunStatus.UPLOADING,
            PipelineRunStatus.UPLOAD_FAILED,
        }:
            raise InvalidVideoError(
                "Загрузка уже завершена или обработка уже началась."
            )
        object_stat = self._storage.stat(run.source_object_key)
        self._repository.add_artifact(
            run_id=run.run_id,
            artifact_type=PipelineArtifactType.SOURCE_VIDEO,
            object_key=run.source_object_key,
            content_type=run.source_content_type or "application/octet-stream",
            size_bytes=object_stat.size,
        )
        updated_run = self._repository.mark_upload_complete(
            run.run_id,
            actual_size_bytes=object_stat.size,
        )
        self._repository.commit()
        if updated_run is None:
            raise PipelineRunNotFoundError("Обработка не найдена.")
        return updated_run

    def list_runs(
        self,
        *,
        page: int,
        page_size: int,
        status: PipelineRunStatus | None,
        city_id: str | None = None,
        route_id: str | None = None,
        assignment_id: str | None = None,
    ) -> PaginatedRunsDTO:
        runs, total = self._repository.list_runs(
            page=page,
            page_size=page_size,
            status=status,
            city_id=city_id,
            route_id=route_id,
            assignment_id=assignment_id,
        )
        return PaginatedRunsDTO(
            items=runs,
            page=page,
            page_size=page_size,
            total=total,
        )

    def get_run(self, run_id: str) -> PipelineRunDTO:
        return self._require_run(run_id)

    def update_shooting(
        self,
        run_id: str,
        *,
        fields: dict[str, object],
    ) -> PipelineRunDTO:
        """Правит реквизиты съёмки: когда снимали и кто снимал.

        Отдельно от обработки: статус, стадия и прогресс сюда не приходят —
        их ведёт воркер, и руками их менять нельзя.
        """
        run = self._repository.update_shooting(run_id, fields=fields)
        if run is None:
            self._repository.rollback()
            raise PipelineRunNotFoundError("Видео не найдено.")
        self._repository.commit()
        return run

    def get_playback(self, run_id: str) -> PlaybackDTO:
        """Ссылка на исходное видео — рамки плеер рисует сам.

        Второй копии видео с вписанными рамками нет намеренно: она весила
        столько же, сколько оригинал, а поверх исходника рамки рисуются из
        `overlay.json` — по ним ещё и кликать можно.
        """
        run = self._require_run(run_id)
        by_type = {item.artifact_type: item for item in run.artifacts}
        source = by_type.get(PipelineArtifactType.SOURCE_VIDEO)
        return PlaybackDTO(
            source_url=(
                self._storage.presigned_get(source.object_key) if source else None
            ),
        )

    def get_overlay(self, run_id: str) -> OverlayPayloadDTO:
        artifact = self._require_artifact(run_id, PipelineArtifactType.OVERLAY)
        payload = json.loads(self._storage.read_text(artifact.object_key))
        return OverlayPayloadDTO.model_validate(payload)

    def get_summary(self, run_id: str) -> RunSummaryDTO:
        """Сводка по брендам с живым β: источник — TRACKS, не BRAND_SUMMARY.

        Бэкенд больше не читает готовый visibility_value из артефакта (там β = 1),
        а считает V = S·α·β сам из зон маршрута, актуальных на момент запроса.
        """
        run = self._require_run(run_id)
        artifact = self._find_artifact(run.artifacts, PipelineArtifactType.TRACKS)
        brands: list[BrandSummaryDTO] = []
        total_objects = 0
        total_visibility = 0.0
        if artifact is not None:
            dataframe = self._read_csv(artifact)
            if not dataframe.empty:
                dataframe = self._filter_business_visible(dataframe)
            if not dataframe.empty:
                intervals = self._repository.get_geozone_intervals(run_id)
                dataframe = self._apply_beta(dataframe, intervals, run.duration_sec)
                brands, total_objects, total_visibility = self._summarize_brands(
                    dataframe
                )
        return RunSummaryDTO(
            run=run,
            totals=RunSummaryTotalsDTO(
                total_objects=total_objects,
                visibility_index=total_visibility,
            ),
            brands=brands,
        )

    def _apply_beta(
        self,
        dataframe: pd.DataFrame,
        intervals: list[GeozoneInterval],
        duration_sec: float | None,
    ) -> pd.DataFrame:
        """Пересчитывает β и итоговую заметность V по геозонам маршрута.

        β = beta(best_timestamp / duration): доля времени → участок → коэффициент.
        V = attention_seconds (S) · confidence_coef (α) · β. Перекрывает значения
        из CSV, где β = 1: источник β — живые зоны, а не артефакт пайплайна.
        Без длительности локализовать объект нельзя — β нейтральный.
        """
        dataframe = dataframe.copy()
        attention = pd.to_numeric(
            dataframe["attention_seconds"], errors="coerce"
        ).fillna(0.0)
        confidence = pd.to_numeric(
            dataframe["confidence_coef"], errors="coerce"
        ).fillna(0.0)
        duration = duration_sec or 0.0
        if duration > 0 and intervals:
            timestamp = pd.to_numeric(
                dataframe["best_timestamp_sec"], errors="coerce"
            ).fillna(0.0)
            fraction = (timestamp / duration).clip(lower=0.0, upper=1.0)
            betas = fraction.map(lambda value: beta(float(value), intervals))
        else:
            betas = pd.Series(1.0, index=dataframe.index)
        dataframe["significance_coef"] = betas
        dataframe["visibility_value"] = attention * confidence * betas
        return dataframe

    def _summarize_brands(
        self,
        dataframe: pd.DataFrame,
    ) -> tuple[list[BrandSummaryDTO], int, float]:
        """Свёртка видимых треков в бренды в два уровня, как в пайплайне.

        Сначала по объекту (фрагменты одного object_id складываются), потом по
        бренду. object_count — число различных объектов, а не фрагментов трека.
        """
        object_level = (
            dataframe.groupby(["object_id", "business_brand"], dropna=False)
            .agg(
                track_fragment_count=("track_id", "count"),
                sum_visibility_value=("visibility_value", "sum"),
                sum_attention_seconds=("attention_seconds", "sum"),
                mean_final_brand_conf=("final_brand_conf", "mean"),
                max_final_brand_conf=("final_brand_conf", "max"),
                first_timestamp_sec=("first_timestamp_sec", "min"),
                last_timestamp_sec=("last_timestamp_sec", "max"),
            )
            .reset_index()
        )
        brand_level = (
            object_level.groupby("business_brand", dropna=False)
            .agg(
                object_count=("object_id", "count"),
                track_fragment_count=("track_fragment_count", "sum"),
                sum_visibility_value=("sum_visibility_value", "sum"),
                sum_attention_seconds=("sum_attention_seconds", "sum"),
                mean_final_brand_conf=("mean_final_brand_conf", "mean"),
                max_final_brand_conf=("max_final_brand_conf", "max"),
                first_timestamp_sec=("first_timestamp_sec", "min"),
                last_timestamp_sec=("last_timestamp_sec", "max"),
            )
            .reset_index()
            .rename(columns={"business_brand": "brand"})
        )
        brands = self._dataframe_models(brand_level, BrandSummaryDTO)
        total_objects = int(len(object_level))
        total_visibility = float(object_level["sum_visibility_value"].sum())
        return brands, total_objects, total_visibility

    def get_objects(
        self,
        run_id: str,
        *,
        limit: int | None,
    ) -> RunObjectsDTO:
        run = self._require_run(run_id)
        artifact = self._find_artifact(run.artifacts, PipelineArtifactType.TRACKS)
        if artifact is None:
            return RunObjectsDTO(run_id=run_id, objects=[])
        dataframe = self._read_csv(artifact)
        if dataframe.empty:
            return RunObjectsDTO(run_id=run_id, objects=[])
        dataframe = self._filter_business_visible(dataframe)
        if dataframe.empty:
            return RunObjectsDTO(run_id=run_id, objects=[])
        intervals = self._repository.get_geozone_intervals(run_id)
        dataframe = self._apply_beta(dataframe, intervals, run.duration_sec)
        dataframe = dataframe.sort_values(
            "visibility_value",
            ascending=False,
        )
        if limit is not None:
            dataframe = dataframe.head(limit)
        rows = self._native_rows(dataframe)
        objects: list[RunObjectDTO] = []
        for row in rows:
            crop_path = str(row.get("best_crop_path") or "")
            object_key = crop_object_key(run_id, crop_path)
            row["crop_url"] = (
                self._storage.presigned_get(object_key) if object_key else None
            )
            objects.append(RunObjectDTO.model_validate(row))
        return RunObjectsDTO(run_id=run_id, objects=objects)

    def get_timeline(
        self,
        run_id: str,
        *,
        bucket_seconds: int,
    ) -> RunTimelineDTO:
        run = self._require_run(run_id)
        artifact = self._find_artifact(
            run.artifacts,
            PipelineArtifactType.DETECTIONS,
        )
        if artifact is None:
            return RunTimelineDTO(
                run_id=run_id,
                bucket_seconds=bucket_seconds,
                points=[],
            )
        dataframe = self._read_csv(artifact)
        if dataframe.empty:
            points: list[RunTimelinePointDTO] = []
        else:
            dataframe = self._filter_business_visible(dataframe)
            if dataframe.empty:
                points = []
            else:
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
                        intensity_sum=("intensity", "sum"),
                    )
                    .reset_index()
                )
                points = self._dataframe_models(grouped, RunTimelinePointDTO)
        return RunTimelineDTO(
            run_id=run_id,
            bucket_seconds=bucket_seconds,
            points=points,
        )

    def _require_run(
        self,
        run_id: str,
        *,
        with_artifacts: bool = True,
        include_hidden: bool = False,
    ) -> PipelineRunDTO:
        run = self._repository.get(
            run_id,
            with_artifacts=with_artifacts,
            include_hidden=include_hidden,
        )
        if run is None:
            raise PipelineRunNotFoundError("Обработка не найдена.")
        return run

    def _require_artifact(
        self,
        run_id: str,
        artifact_type: PipelineArtifactType,
    ) -> PipelineArtifactDTO:
        run = self._require_run(run_id)
        artifact = self._find_artifact(run.artifacts, artifact_type)
        if artifact is None:
            raise PipelineRunNotFoundError("Файл результата не найден.")
        return artifact

    @staticmethod
    def _find_artifact(
        artifacts: list[PipelineArtifactDTO],
        artifact_type: PipelineArtifactType,
    ) -> PipelineArtifactDTO | None:
        return next(
            (
                artifact
                for artifact in artifacts
                if artifact.artifact_type == artifact_type
            ),
            None,
        )

    def _read_csv(self, artifact: PipelineArtifactDTO) -> pd.DataFrame:
        value = self._storage.read_bytes(artifact.object_key)
        if not value:
            return pd.DataFrame()
        try:
            return pd.read_csv(io.BytesIO(value), keep_default_na=False)
        except EmptyDataError:
            return pd.DataFrame()

    @staticmethod
    def _native_rows(dataframe: pd.DataFrame) -> list[dict[str, Any]]:
        return json.loads(dataframe.to_json(orient="records", force_ascii=False))

    def _dataframe_models(
        self,
        dataframe: pd.DataFrame,
        model: type[ModelT],
    ) -> list[ModelT]:
        return [model.model_validate(row) for row in self._native_rows(dataframe)]

    @staticmethod
    def _filter_business_visible(dataframe: pd.DataFrame) -> pd.DataFrame:
        if "business_visible" not in dataframe.columns:
            return dataframe
        visible = pd.to_numeric(
            dataframe["business_visible"],
            errors="coerce",
        ).fillna(0)
        return dataframe.loc[visible > 0].copy()
