from __future__ import annotations

from collections.abc import Iterable
from typing import NamedTuple

# Вне размеченных участков значимость нейтральна: умножение на 1 не меняет балл.
NEUTRAL_BETA = 1.0


class GeozoneInterval(NamedTuple):
    """Участок значимости в долях времени видео: [start, end) и множитель β."""

    start_fraction: float
    end_fraction: float
    coefficient: float


def beta(fraction: float, intervals: Iterable[GeozoneInterval]) -> float:
    """Коэффициент значимости места для объекта по его доле времени видео.

    Полуинтервал [start, end): начало включается, конец — нет, поэтому смежные
    участки не спорят за точку стыка. Вне всех участков — нейтральный 1.0.
    Пересечений нет (запрещены при разметке), значит подходит не более одного.
    """
    for interval in intervals:
        if interval.start_fraction <= fraction < interval.end_fraction:
            return interval.coefficient
    return NEUTRAL_BETA


def overlaps(start: float, end: float, intervals: Iterable[GeozoneInterval]) -> bool:
    """Пересекается ли участок [start, end) хоть с одним из существующих.

    Полуинтервалы налезают, когда каждый начинается раньше конца другого. Стык
    (конец одного = начало другого) пересечением не считается — это и есть смысл
    полуинтервала, ради которого смежные зоны можно ставить впритык.
    """
    return any(
        start < interval.end_fraction and interval.start_fraction < end
        for interval in intervals
    )
