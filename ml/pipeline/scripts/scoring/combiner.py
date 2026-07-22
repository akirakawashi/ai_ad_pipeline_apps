"""Сборка итогового балла объекта: V = S · α · β.

Секунды внимания (физика видимости) × уверенность × значимость места.
"""

from __future__ import annotations


def visibility_value(
    attention_seconds: float,
    confidence_coef: float,
    significance_coef: float,
) -> float:
    return attention_seconds * confidence_coef * significance_coef
