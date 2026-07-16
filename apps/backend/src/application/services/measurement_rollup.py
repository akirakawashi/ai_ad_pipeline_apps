"""Свёртка проездов в метрики замера.

Единственное место, где решается, КАК считается замер. Слой проездов
(MeasurementPassDTO) от этого не зависит и остаётся тем же, если политика
поменяется: среднее вместо медианы, отбраковка коротких проездов, нормировка.

Сейчас: среднее по всем готовым проездам плюс разброс между ними.
Разброс не украшение — он показывает, можно ли верить замеру.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import fmean, stdev

from application.common.dto import (
    MeasurementBrandDTO,
    MeasurementPassDTO,
    MeasurementStatDTO,
    MeasurementTotalsDTO,
)


def _stat(values: list[float]) -> MeasurementStatDTO:
    if not values:
        return MeasurementStatDTO()
    # stdev требует минимум двух точек; на одном проезде разброса просто нет.
    return MeasurementStatDTO(
        mean=fmean(values),
        std=stdev(values) if len(values) > 1 else 0.0,
    )


def rollup_totals(
    passes: list[MeasurementPassDTO],
    *,
    passes_total: int,
) -> MeasurementTotalsDTO:
    return MeasurementTotalsDTO(
        passes_total=passes_total,
        passes_completed=len(passes),
        duration_sec=sum(item.duration_sec for item in passes),
        objects_per_pass=_stat([float(item.objects_count) for item in passes]),
        visibility_per_pass=_stat([item.visibility_index for item in passes]),
    )


def rollup_brands(passes: list[MeasurementPassDTO]) -> list[MeasurementBrandDTO]:
    if not passes:
        return []

    brands = {brand.brand for item in passes for brand in item.brands}
    objects: dict[str, list[float]] = defaultdict(list)
    visibility: dict[str, list[float]] = defaultdict(list)

    for item in passes:
        by_brand = {brand.brand: brand for brand in item.brands}
        for brand in brands:
            # Бренда нет в проезде — это ноль, а не пропуск: иначе среднее
            # завысится на брендах, которые попались только в одном проезде.
            found = by_brand.get(brand)
            objects[brand].append(float(found.objects_count) if found else 0.0)
            visibility[brand].append(found.visibility_index if found else 0.0)

    rows = [
        MeasurementBrandDTO(
            brand=brand,
            objects_per_pass=_stat(objects[brand]),
            visibility_per_pass=_stat(visibility[brand]),
        )
        for brand in brands
    ]

    total_visibility = sum(row.visibility_per_pass.mean for row in rows)
    if total_visibility > 0:
        for row in rows:
            row.visibility_share = row.visibility_per_pass.mean / total_visibility

    rows.sort(key=lambda row: row.visibility_per_pass.mean, reverse=True)
    return rows
