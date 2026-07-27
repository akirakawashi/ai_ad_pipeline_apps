"""Свёртка съёмок в метрики задания.

Единственное место, где решается, КАК считается задание. Слой съёмок
(ShootingMetricsDTO) от этого не зависит и остаётся тем же, если политика
поменяется: среднее вместо медианы, отбраковка коротких съёмок, нормировка.

Сейчас: среднее по всем готовым съёмкам плюс разброс между ними.
Разброс не украшение — он показывает, можно ли верить заданию.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import fmean, stdev

from application.common.dto import (
    AssignmentBrandDTO,
    ShootingMetricsDTO,
    AssignmentStatDTO,
    AssignmentTotalsDTO,
)


def _stat(values: list[float]) -> AssignmentStatDTO:
    if not values:
        return AssignmentStatDTO()
    # stdev требует минимум двух точек; на одной съёмке разброса просто нет.
    return AssignmentStatDTO(
        mean=fmean(values),
        std=stdev(values) if len(values) > 1 else 0.0,
    )


def rollup_totals(
    shootings: list[ShootingMetricsDTO],
    *,
    shootings_total: int,
) -> AssignmentTotalsDTO:
    return AssignmentTotalsDTO(
        shootings_total=shootings_total,
        shootings_completed=len(shootings),
        duration_sec=sum(item.duration_sec for item in shootings),
        objects_per_shooting=_stat([float(item.objects_count) for item in shootings]),
        visibility_per_shooting=_stat([item.visibility_index for item in shootings]),
    )


def rollup_brands(shootings: list[ShootingMetricsDTO]) -> list[AssignmentBrandDTO]:
    if not shootings:
        return []

    brands = {brand.brand for item in shootings for brand in item.brands}
    objects: dict[str, list[float]] = defaultdict(list)
    visibility: dict[str, list[float]] = defaultdict(list)

    for item in shootings:
        by_brand = {brand.brand: brand for brand in item.brands}
        for brand in brands:
            # Бренда нет в съёмке — это ноль, а не пропуск: иначе среднее
            # завысится на брендах, которые попались только в одной съёмке.
            found = by_brand.get(brand)
            objects[brand].append(float(found.objects_count) if found else 0.0)
            visibility[brand].append(found.visibility_index if found else 0.0)

    rows = [
        AssignmentBrandDTO(
            brand=brand,
            objects_per_shooting=_stat(objects[brand]),
            visibility_per_shooting=_stat(visibility[brand]),
        )
        for brand in brands
    ]

    total_visibility = sum(row.visibility_per_shooting.mean for row in rows)
    if total_visibility > 0:
        for row in rows:
            row.visibility_share = row.visibility_per_shooting.mean / total_visibility

    rows.sort(key=lambda row: row.visibility_per_shooting.mean, reverse=True)
    return rows
