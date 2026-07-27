"""Мгновенная интенсивность внимания на кадр: I = A · P · C.

Перемножение (AND-логика): слабый любой из факторов → слабый момент.
"""

from __future__ import annotations


def intensity(area_coef: float, position_coef: float, contrast_coef: float) -> float:
    return area_coef * position_coef * contrast_coef
