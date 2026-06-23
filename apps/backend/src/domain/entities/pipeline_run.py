from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PipelineRun:
    run_id: str
    path: Path
    source_path: str | None
    source_name: str | None
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
class RunArtifact:
    name: str
    relative_path: str
    media_type: str
    size_bytes: int

