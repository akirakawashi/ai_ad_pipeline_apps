"""Свёртка съёмок в метрики уровня выше: задания и маршрута.

Единственное место, где решается, КАК считается уровень выше съёмки. Слой съёмок
(ShootingMetricsDTO) от этого не зависит и остаётся тем же, если политика
поменяется: среднее вместо медианы, отбраковка коротких съёмок, нормировка.

Один и тот же код обслуживает оба уровня: разница только в том, какой список ему
дать — съёмки одного задания или все съёмки маршрута. **Маршрут считается из
съёмок напрямую, а не из результатов заданий**, иначе задание из двух проездов
весило бы столько же, сколько задание из двадцати.

Сейчас: по всем готовым съёмкам считаются обе оценки центра — среднее и медиана,
— плюс разброс между съёмками. Какую из двух показать, решает интерфейс: список
съёмок для них один и тот же, и ходить на сервер ради переключения незачем.
Разброс не украшение — он показывает, можно ли верить цифре.

Отбраковки нет: все обработанные съёмки идут в свёртку как есть. Держится это на
допущении, что видео покрывает проезд целиком от А до Б.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import fmean, median, stdev

from application.common.dto import (
    MetricStatDTO,
    RollupBrandDTO,
    RollupTotalsDTO,
    ShootingMetricsDTO,
)


def _stat(values: list[float]) -> MetricStatDTO:
    if not values:
        return MetricStatDTO()
    # stdev требует минимум двух точек; на одной съёмке разброса просто нет.
    return MetricStatDTO(
        mean=fmean(values),
        median=median(values),
        std=stdev(values) if len(values) > 1 else 0.0,
    )


def rollup_totals(
    shootings: list[ShootingMetricsDTO],
    *,
    shootings_total: int,
) -> RollupTotalsDTO:
    return RollupTotalsDTO(
        shootings_total=shootings_total,
        shootings_completed=len(shootings),
        duration_sec=sum(item.duration_sec for item in shootings),
        objects_per_shooting=_stat([float(item.objects_count) for item in shootings]),
        visibility_per_shooting=_stat([item.visibility_index for item in shootings]),
    )


def rollup_brands(shootings: list[ShootingMetricsDTO]) -> list[RollupBrandDTO]:
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
        RollupBrandDTO(
            brand=brand,
            objects_per_shooting=_stat(objects[brand]),
            visibility_per_shooting=_stat(visibility[brand]),
        )
        for brand in brands
    ]

    # Порядок по среднему, а не по выбранной оценке: он закрепляет за брендом
    # место на графике, и столбцы не прыгают при переключении тумблера.
    rows.sort(key=lambda row: row.visibility_per_shooting.mean, reverse=True)
    return rows
