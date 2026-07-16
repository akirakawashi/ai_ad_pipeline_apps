from __future__ import annotations

from enum import StrEnum


class CropQualityStatus(StrEnum):
    PASSED = "passed"
    BORDERLINE = "borderline"
    REJECTED = "rejected"


class ClassificationInputStatus(StrEnum):
    ACCEPTED = "accepted"
    BORDERLINE = "borderline"
    REJECTED = "rejected"


class BrandStatus(StrEnum):
    NOT_CLASSIFIED = "not_classified"
    UNKNOWN = "unknown"
    MANUAL_REVIEW = "manual_review"
    DETECTED_BRAND = "detected_brand"
    OTHER = "other"


class FinalStatus(StrEnum):
    NOT_CLASSIFIED = "not_classified"
    UNKNOWN = "unknown"
    MANUAL_REVIEW = "manual_review"
    DETECTED_BRAND = "detected_brand"
    OTHER = "other"


OTHER_BRAND = "other"
TARGET_BRANDS = frozenset({"mts", "plus7", "miranda"})


def normalize_brand_name(value: str) -> str:
    normalized = value.strip().lower()
    return "plus7" if normalized == "+7" else normalized
