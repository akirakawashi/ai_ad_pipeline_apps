"""Write overlay viewer artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..config import PipelineConfig
from ..schemas import DetectionRecord, InputMetadata, TrackRecord
from .payload import build_overlay_payload
from .template import render_viewer_html


def write_html_overlay_viewer(
    output_dir: Path,
    metadata: InputMetadata,
    detections: list[DetectionRecord],
    tracks: list[TrackRecord],
    config: PipelineConfig,
) -> None:
    if metadata.input_type != "video":
        return

    overlay = build_overlay_payload(output_dir, metadata, detections, tracks, config)
    write_json(output_dir / "overlay.json", overlay)
    (output_dir / "viewer.html").write_text(
        render_viewer_html(overlay), encoding="utf-8"
    )


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
