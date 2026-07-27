"""Кусочно-линейная интерполяция по опорным точкам — общая для факторов.

Между точками — линейная интерполяция. Ниже первой точки и выше последней —
клэмп к крайним значениям (без экстраполяции). Точки отсортированы по x.
Используется площадью (Шаг 1) и далее положением/контрастом/уверенностью.
"""

from __future__ import annotations

from collections.abc import Sequence


def piecewise_linear(x: float, points: Sequence[tuple[float, float]]) -> float:
    if not points:
        raise ValueError("нужна хотя бы одна опорная точка")
    if x <= points[0][0]:
        return points[0][1]
    if x >= points[-1][0]:
        return points[-1][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= x <= x1:
            if x1 == x0:
                return y1
            t = (x - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)
    return points[-1][1]
