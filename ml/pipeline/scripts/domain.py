"""Compatibility facade for shared pipeline domain values."""

from __future__ import annotations

from pipeline_contracts.domain import (
    OTHER_BRAND,
    TARGET_BRANDS,
    BrandStatus,
    ClassificationInputStatus,
    CropQualityStatus,
    FinalStatus,
    normalize_brand_name,
)

__all__ = [
    "OTHER_BRAND",
    "TARGET_BRANDS",
    "BrandStatus",
    "ClassificationInputStatus",
    "CropQualityStatus",
    "FinalStatus",
    "normalize_brand_name",
]
