from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PipelineRunDTO:
    run_id: str
    source_name: str | None
    source_path: str | None
    input_type: str | None
    fps: float | None
    frame_count: int | None
    frame_stride: int | None
    duration_sec: float | None
    width: int | None
    height: int | None
    created_at: float
    has_overlay: bool
    has_viewer: bool
    has_report: bool
    has_annotated_video: bool


@dataclass(frozen=True)
class RunArtifactDTO:
    name: str
    relative_path: str
    media_type: str
    size_bytes: int


@dataclass(frozen=True)
class RunSummaryDTO:
    run: PipelineRunDTO
    totals: dict[str, Any]
    brands: list[dict[str, Any]]
    artifacts: list[RunArtifactDTO]


@dataclass(frozen=True)
class RunObjectsDTO:
    run_id: str
    objects: list[dict[str, Any]]


@dataclass(frozen=True)
class RunTimelineDTO:
    run_id: str
    bucket_seconds: int
    points: list[dict[str, Any]]

