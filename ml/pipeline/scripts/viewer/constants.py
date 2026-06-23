"""Viewer brand presentation settings."""

from __future__ import annotations

from ..domain import TARGET_BRANDS

BRAND_STYLES = {
    "mts": {"label": "MTS", "color": "#ff3b30"},
    "plus7": {"label": "PLUS7", "color": "#38bdf8"},
    "miranda": {"label": "MIRANDA", "color": "#22c55e"},
    "other": {"label": "OTHER", "color": "#ffe600"},
}

__all__ = ["BRAND_STYLES", "TARGET_BRANDS"]
