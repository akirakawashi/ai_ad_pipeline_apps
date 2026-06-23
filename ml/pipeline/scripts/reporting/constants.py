"""Shared report labels, colors, and chart settings."""

from __future__ import annotations

from ..domain import TARGET_BRANDS as DOMAIN_TARGET_BRANDS

BRAND_LABELS = {
    "mts": "МТС",
    "miranda": "Миранда",
    "plus7": "+7",
    "other": "Другая реклама",
}
BRAND_COLORS = {
    "mts": "#ff3b30",
    "miranda": "#22c55e",
    "plus7": "#38bdf8",
    "other": "#facc15",
}
BRAND_ORDER = ["mts", "miranda", "plus7", "other"]
TARGET_BRANDS = [brand for brand in BRAND_ORDER if brand in DOMAIN_TARGET_BRANDS]
TIMELINE_BUCKET_SECONDS = 10
