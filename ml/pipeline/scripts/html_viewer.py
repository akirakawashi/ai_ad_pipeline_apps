"""Compatibility facade for HTML overlay viewer generation."""

from __future__ import annotations

from .viewer.payload import (
    build_overlay_payload,
    card_priority,
    detection_to_overlay_object,
    frame_timestamp,
    relative_video_source,
)
from .viewer.template import render_viewer_html
from .viewer.writer import write_html_overlay_viewer, write_json

__all__ = [
    "build_overlay_payload",
    "card_priority",
    "detection_to_overlay_object",
    "frame_timestamp",
    "relative_video_source",
    "render_viewer_html",
    "write_html_overlay_viewer",
    "write_json",
]
