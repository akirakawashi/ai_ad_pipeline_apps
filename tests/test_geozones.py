"""Чистая математика геозон: β по доле времени и запрет пересечений.

Без БД и без моделей — только domain.geozones. Полуинтервал [start, end):
начало включается, конец нет, поэтому смежные участки ставятся впритык и не
спорят за точку стыка. Вне размеченного — нейтральный β = 1.0.
"""

from __future__ import annotations

from domain.geozones import GeozoneInterval, beta, overlaps

CITY = GeozoneInterval(0.20, 0.35, 1.2)
CENTER = GeozoneInterval(0.35, 0.60, 1.5)
INTERVALS = (CITY, CENTER)


class TestBeta:
    def test_empty_intervals_is_neutral(self):
        assert beta(0.5, ()) == 1.0

    def test_inside_interval_returns_its_coefficient(self):
        assert beta(0.50, INTERVALS) == 1.5
        assert beta(0.25, INTERVALS) == 1.2

    def test_start_edge_is_included(self):
        """Ровно на начале участок уже действует."""
        assert beta(0.35, INTERVALS) == 1.5
        assert beta(0.20, INTERVALS) == 1.2

    def test_end_edge_is_excluded(self):
        """Ровно на конце участок уже НЕ действует — это точка стыка."""
        # 0.35 — конец «Города» и начало «Центра»: побеждает начало.
        assert beta(0.35, (CITY,)) == 1.0
        # 0.60 — конец «Центра», дальше ничего: нейтрально.
        assert beta(0.60, INTERVALS) == 1.0

    def test_hole_between_intervals_is_neutral(self):
        gapped = (GeozoneInterval(0.1, 0.2, 1.3), GeozoneInterval(0.5, 0.6, 1.4))
        assert beta(0.35, gapped) == 1.0

    def test_before_all_intervals_is_neutral(self):
        assert beta(0.05, INTERVALS) == 1.0

    def test_after_all_intervals_is_neutral(self):
        assert beta(0.95, INTERVALS) == 1.0

    def test_boundaries_zero_and_one(self):
        full = (GeozoneInterval(0.0, 1.0, 2.0),)
        assert beta(0.0, full) == 2.0  # начало включено
        assert beta(0.999, full) == 2.0
        assert beta(1.0, full) == 1.0  # конец исключён

    def test_coefficient_below_one_passes_through(self):
        weak = (GeozoneInterval(0.4, 0.5, 0.7),)
        assert beta(0.45, weak) == 0.7


class TestOverlaps:
    def test_empty_never_overlaps(self):
        assert overlaps(0.1, 0.9, ()) is False

    def test_disjoint_does_not_overlap(self):
        assert overlaps(0.7, 0.8, INTERVALS) is False

    def test_touching_at_edge_does_not_overlap(self):
        """Стык конец-в-начало — не пересечение: смысл полуинтервала."""
        assert overlaps(0.60, 0.80, INTERVALS) is False  # начинается на конце «Центра»
        assert overlaps(0.10, 0.20, INTERVALS) is False  # кончается на начале «Города»

    def test_partial_overlap_is_detected(self):
        assert overlaps(0.50, 0.70, INTERVALS) is True

    def test_contained_interval_overlaps(self):
        assert overlaps(0.40, 0.45, INTERVALS) is True

    def test_containing_interval_overlaps(self):
        assert overlaps(0.0, 1.0, INTERVALS) is True

    def test_identical_interval_overlaps(self):
        assert overlaps(0.35, 0.60, INTERVALS) is True
