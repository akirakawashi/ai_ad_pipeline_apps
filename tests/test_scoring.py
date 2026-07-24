"""Метрика заметности: I = A·P·C → S = Σ(I·Δt) → V = S·α·β.

Чистые функции без БД и без моделей. Числа в таблицах — настроечные, поэтому
проверяем не их самих, а свойства: клэмп за краями, монотонность, попадание в
опорные точки, интерполяцию между ними и итоговую сборку.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from ml.pipeline.scripts.config import PipelineConfig
from ml.pipeline.scripts.schemas import DetectionRecord, FrameRecord
from ml.pipeline.scripts.scoring import fill_detection_scoring
from ml.pipeline.scripts.scoring.area import area_coefficient
from ml.pipeline.scripts.scoring.attention import attention_seconds
from ml.pipeline.scripts.scoring.confidence import confidence_coefficient
from ml.pipeline.scripts.scoring.contrast import contrast_coefficient
from ml.pipeline.scripts.scoring.geometry import fill_geometry
from ml.pipeline.scripts.scoring.intensity import intensity
from ml.pipeline.scripts.scoring.interpolation import piecewise_linear


@pytest.fixture
def config() -> PipelineConfig:
    return PipelineConfig(
        input_path=Path("in.mp4"),
        output_dir=Path("out"),
        detector_model_path=Path("det.pt"),
        classifier_model_path=Path("cls.pt"),
        run_id="test",
    )


def make_frame(image: np.ndarray, *, delta_t: float = 0.4) -> FrameRecord:
    height, width = image.shape[:2]
    return FrameRecord(
        frame_index=0,
        timestamp_sec=0.0,
        width=width,
        height=height,
        delta_t_sec=delta_t,
        image=image,
    )


def make_detection(
    *,
    bbox: tuple[float, float, float, float] = (0.0, 0.0, 10.0, 10.0),
    area_ratio: float = 0.02,
    delta_t: float = 0.4,
) -> DetectionRecord:
    x1, y1, x2, y2 = bbox
    return DetectionRecord(
        run_id="test",
        source_path="in.mp4",
        input_type="video",
        frame_index=0,
        timestamp_sec=0.0,
        sample_delta_t_sec=delta_t,
        det_index=0,
        track_id=1,
        det_class="ad",
        det_conf=0.9,
        bbox_x1=x1,
        bbox_y1=y1,
        bbox_x2=x2,
        bbox_y2=y2,
        bbox_width=x2 - x1,
        bbox_height=y2 - y1,
        bbox_aspect_ratio=(x2 - x1) / max(1.0, y2 - y1),
        bbox_area=(x2 - x1) * (y2 - y1),
        area_ratio=area_ratio,
        center_x=0.0,
        center_y=0.0,
        center_x_norm=0.0,
        center_y_norm=0.0,
    )


# --- интерполяция ---------------------------------------------------------


class TestPiecewiseLinear:
    POINTS = ((0.0, 10.0), (1.0, 20.0), (2.0, 40.0))

    def test_clamps_below_first_point(self):
        assert piecewise_linear(-5.0, self.POINTS) == 10.0

    def test_clamps_above_last_point(self):
        """За последней точкой не экстраполируем: значение замирает."""
        assert piecewise_linear(100.0, self.POINTS) == 40.0

    def test_hits_anchor_points_exactly(self):
        for x, y in self.POINTS:
            assert piecewise_linear(x, self.POINTS) == y

    def test_interpolates_between_points(self):
        assert piecewise_linear(0.5, self.POINTS) == 15.0
        assert piecewise_linear(1.5, self.POINTS) == 30.0

    def test_single_point_is_constant(self):
        assert piecewise_linear(42.0, ((1.0, 7.0),)) == 7.0

    def test_empty_points_rejected(self):
        with pytest.raises(ValueError):
            piecewise_linear(1.0, ())


# --- площадь --------------------------------------------------------------


class TestArea:
    def test_tiny_object_gets_floor_not_zero(self, config):
        """Мелкий объект всё равно видели: в ноль не проваливаемся."""
        floor = config.scoring.area.points[0][1]
        assert area_coefficient(0.0001, config) == floor
        assert floor > 0

    def test_large_object_caps_at_one(self, config):
        assert area_coefficient(0.5, config) == 1.0

    def test_monotonic_by_area(self, config):
        ratios = [0.001, 0.005, 0.01, 0.02, 0.035, 0.05, 0.2]
        values = [area_coefficient(r, config) for r in ratios]
        assert values == sorted(values)


# --- положение ------------------------------------------------------------


class TestPosition:
    def test_own_side_beats_oncoming(self, config):
        """Правостороннее движение: своя сторона справа и весит больше."""
        own = position_at(0.67, config)
        oncoming = position_at(0.33, config)
        assert own > oncoming

    def test_peak_is_near_center_not_at_edge(self, config):
        """Пик — у центра со своей стороны, не на периферии кадра."""
        assert position_at(0.67, config) > position_at(1.0, config)

    def test_left_hand_traffic_mirrors_curve(self, config):
        left = replace(config, scoring=replace(config.scoring, handedness="left"))
        assert position_at(0.33, left) == pytest.approx(position_at(0.67, config))
        assert position_at(0.0, left) == pytest.approx(position_at(1.0, config))

    def test_height_ignored_in_v1(self, config):
        from ml.pipeline.scripts.scoring.position import position_coefficient

        assert position_coefficient(0.67, 0.1, config) == position_coefficient(
            0.67, 0.9, config
        )


def position_at(x: float, config: PipelineConfig) -> float:
    from ml.pipeline.scripts.scoring.position import position_coefficient

    return position_coefficient(x, 0.5, config)


# --- контраст -------------------------------------------------------------


class TestContrast:
    def test_bright_object_on_dark_background_scores_high(self, config):
        image = np.zeros((100, 100, 3), dtype=np.uint8)
        image[40:60, 40:60] = 255
        detection = make_detection(bbox=(40, 40, 60, 60))
        assert contrast_coefficient(detection, make_frame(image), config) == 1.0

    def test_object_blending_into_background_gets_floor(self, config):
        floor = config.scoring.contrast.points[0][1]
        image = np.full((100, 100, 3), 128, dtype=np.uint8)
        detection = make_detection(bbox=(40, 40, 60, 60))
        assert contrast_coefficient(detection, make_frame(image), config) == floor

    def test_missing_image_falls_back_to_floor(self, config):
        floor = config.scoring.contrast.points[0][1]
        frame = make_frame(np.zeros((10, 10, 3), dtype=np.uint8))
        frame.image = None
        assert contrast_coefficient(make_detection(), frame, config) == floor

    def test_degenerate_bbox_falls_back_to_floor(self, config):
        floor = config.scoring.contrast.points[0][1]
        image = np.zeros((100, 100, 3), dtype=np.uint8)
        detection = make_detection(bbox=(50, 50, 50, 50))
        assert contrast_coefficient(detection, make_frame(image), config) == floor

    def test_channel_order_does_not_matter(self, config):
        """Яркость — среднее по каналам, поэтому RGB и BGR дают одно и то же."""
        rgb = np.zeros((100, 100, 3), dtype=np.uint8)
        rgb[40:60, 40:60] = (200, 100, 50)
        bgr = rgb[:, :, ::-1].copy()
        detection = make_detection(bbox=(40, 40, 60, 60))
        assert contrast_coefficient(
            detection, make_frame(rgb), config
        ) == contrast_coefficient(detection, make_frame(bgr), config)


# --- уверенность ----------------------------------------------------------


class TestConfidence:
    def test_low_confidence_gets_floor(self, config):
        """Объект видели даже при слабой классификации — в ноль не режем."""
        floor = config.scoring.confidence.points[0][1]
        assert confidence_coefficient([], 0.0, config) == floor
        assert floor == 0.5

    def test_high_confidence_caps_at_one(self, config):
        assert confidence_coefficient([], 0.99, config) == 1.0

    def test_monotonic_by_confidence(self, config):
        values = [confidence_coefficient([], c, config) for c in (0.3, 0.5, 0.8, 0.95)]
        assert values == sorted(values)


# --- сборка ---------------------------------------------------------------


class TestComposition:
    def test_intensity_is_product_of_three(self):
        assert intensity(0.9, 0.8, 1.0) == pytest.approx(0.72)

    def test_attention_integrates_intensity_over_time(self):
        """Δt — ось интегрирования: время не отдельный множитель."""
        detections = [
            make_detection(delta_t=0.4),
            make_detection(delta_t=0.4),
            make_detection(delta_t=0.2),
        ]
        for detection, value in zip(detections, (0.5, 1.0, 1.0)):
            detection.intensity = value
        assert attention_seconds(detections) == pytest.approx(0.8)

    def test_geometry_normalises_center(self):
        detection = make_detection(bbox=(0, 0, 100, 50))
        fill_geometry(detection, make_frame(np.zeros((200, 400, 3), dtype=np.uint8)))
        assert detection.center_x == 50.0
        assert detection.center_x_norm == pytest.approx(0.125)
        assert detection.center_y_norm == pytest.approx(0.125)

    def test_end_to_end_frame_to_base_visibility(self, config):
        """Сквозной проход: A·P·C → интенсивность → секунды внимания → S·α.

        Дальше β и итог V = S·α·β накладывает бэкенд из геозон — пайплайн до них
        не доходит, поэтому и проверяем только физику.
        """
        image = np.zeros((100, 100, 3), dtype=np.uint8)
        image[40:60, 60:80] = 255
        frame = make_frame(image)
        detection = make_detection(bbox=(60, 40, 80, 60), area_ratio=0.04, delta_t=0.2)

        fill_detection_scoring(detection, frame, config)

        assert detection.intensity == pytest.approx(
            detection.area_coef * detection.position_coef * detection.contrast_coef
        )
        seconds = attention_seconds([detection])
        assert seconds == pytest.approx(detection.intensity * 0.2)

        alpha = confidence_coefficient([detection], 0.85, config)
        assert 0.0 < alpha <= 1.0
        assert seconds * alpha > 0.0
