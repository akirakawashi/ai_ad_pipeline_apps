"""Common dataframe and formatting helpers for reports."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .constants import BRAND_COLORS, BRAND_LABELS, BRAND_ORDER


def filter_business_visible(dataframe: pd.DataFrame) -> pd.DataFrame:
    if dataframe.empty or "business_visible" not in dataframe.columns:
        return dataframe.iloc[0:0].copy()
    visible = (
        pd.to_numeric(dataframe["business_visible"], errors="coerce")
        .fillna(0)
        .astype(int)
        == 1
    )
    return dataframe[visible].copy()


def normalize_brand_series(series: pd.Series) -> pd.Series:
    return series.fillna("other").replace({"": "other"}).astype(str)


def brand_label(brand: str) -> str:
    return BRAND_LABELS.get(brand, brand)


def brand_order(brand: str) -> int:
    try:
        return BRAND_ORDER.index(brand)
    except ValueError:
        return len(BRAND_ORDER)


def label_color_map() -> dict[str, str]:
    return {brand_label(brand): color for brand, color in BRAND_COLORS.items()}


def ordered_labels(brands: list[str] | None = None) -> list[str]:
    if brands is None:
        brands = BRAND_ORDER
    return [brand_label(brand) for brand in brands]


def format_chart_number(value: Any) -> str:
    numeric_value = float(value)
    if abs(numeric_value) >= 10:
        return f"{numeric_value:.1f}"
    return f"{numeric_value:.2f}"


def format_chart_time(seconds: Any) -> str:
    total = max(0, int(float(seconds)))
    minutes = total // 60
    rest = total % 60
    return f"{minutes:02d}:{rest:02d}"
