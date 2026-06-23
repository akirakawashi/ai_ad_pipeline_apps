"""HTML template loader for the overlay viewer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TEMPLATE_PATH = Path(__file__).with_name("overlay_viewer.html")


def render_viewer_html(overlay: dict[str, Any]) -> str:
    overlay_json = json.dumps(
        overlay, ensure_ascii=False, separators=(",", ":")
    ).replace("</", "<\\/")
    return TEMPLATE_PATH.read_text(encoding="utf-8").replace(
        "__OVERLAY_JSON__", overlay_json
    )
