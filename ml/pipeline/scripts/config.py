"""Pipeline configuration grouped by processing responsibility."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_FRAME_STRIDE = 10


@dataclass(frozen=True)
class DetectionConfig:
    confidence_min: float = 0.50
    image_size: int | None = 960
    iou: float = 0.50
    min_width: int = 48
    min_height: int = 40
    min_area_ratio: float = 0.001
    min_aspect_ratio: float = 0.25
    max_aspect_ratio: float = 8.0


@dataclass(frozen=True)
class CropQualityConfig:
    pass_min: float = 0.65
    borderline_min: float = 0.40
    blur_pass_variance: float = 120.0
    blur_borderline_variance: float = 35.0
    brightness_min: float = 35.0
    brightness_max: float = 225.0


@dataclass(frozen=True)
class ClassificationConfig:
    min_width: int = 120
    min_height: int = 60
    min_area_ratio: float = 0.002
    crop_margin_ratio: float = 0.05
    brand_confidence_accept: float = 0.80
    other_confidence_accept: float = 0.85
    manual_review_min: float = 0.40
    conflict_margin: float = 0.10
    best_crops_per_object: int = 3


@dataclass(frozen=True)
class TrackingConfig:
    iou_min: float = 0.35
    max_gap_frames: int = 2
    min_detections: int = 2
    min_frame_span: int = 10
    object_merge_max_gap_frames: int = 90
    object_merge_min_iou: float = 0.02
    object_merge_max_center_distance: float = 0.18
    object_merge_max_area_ratio: float = 5.0
    object_merge_max_aspect_ratio: float = 3.0


@dataclass(frozen=True)
class BusinessConfig:
    min_object_detections: int = 3
    min_visible_duration_sec: float = 0.50


@dataclass(frozen=True)
class AreaConfig:
    """Тир-таблица площади: (доля кадра, коэффициент A).

    Между точками — линейная интерполяция; ниже первой и выше последней — клэмп
    к крайним значениям (мелкие не проваливаются в 0, крупные не растут выше 1).
    Числа — дефолт, бизнес тюнит.
    """

    points: tuple[tuple[float, float], ...] = (
        (0.005, 0.30),  # 0.5% кадра → 0.30
        (0.02, 0.70),   # 2%  кадра → 0.70
        (0.05, 1.00),   # 5%  кадра → 1.00 (и крупнее — тоже 1.00)
    )


@dataclass(frozen=True)
class PositionConfig:
    """Кривая положения по горизонтали (экран-X, доля ширины) → коэффициент P.

    Точки заданы для ПРАВОСТОРОННЕГО движения: своя сторона = правая (большой x),
    встречная = левая (малый x). Для левостороннего движения кривая зеркалится
    (см. handedness). Пик — на своей стороне ближе к центру, не на краю.
    Линейная интерполяция между точками, за краями — клэмп. Бизнес тюнит.
    v1: только горизонталь (высоту center_y_norm пока не учитываем).
    """

    points: tuple[tuple[float, float], ...] = (
        (0.00, 0.50),  # левый край — встречная периферия
        (0.33, 0.60),  # встречная, ближе к центру
        (0.50, 0.80),  # центр кадра (точка схода) — переход
        (0.67, 1.00),  # своя сторона у центра — пик
        (0.85, 0.85),  # своя, средняя зона
        (1.00, 0.70),  # своя периферия (правый край)
    )


@dataclass(frozen=True)
class ContrastConfig:
    """Контраст щита к фону по яркости (кольцо вокруг bbox), v1.

    ring_margin_ratio — насколько расширяем bbox под кольцо-фон (доля стороны).
    points — (яркостной контраст Михельсона 0…1) → коэффициент C, интерполяция.
    Числа условные, бизнес тюнит.
    """

    ring_margin_ratio: float = 0.5
    points: tuple[tuple[float, float], ...] = (
        (0.05, 0.60),  # сливается с фоном
        (0.15, 0.80),  # средний контраст
        (0.35, 1.00),  # ярко выделяется (и выше — 1.0)
    )


@dataclass(frozen=True)
class ConfidenceConfig:
    """Коэффициент уверенности α из уверенности бренда (final_brand_conf).

    Таблица (уверенность → α) с интерполяцией, за краями клэмп. Пол 0.5 — объект
    всё равно видели, в ноль не режем. v1: только величина, без стабильности бренда.
    """

    points: tuple[tuple[float, float], ...] = (
        (0.40, 0.50),  # низкая уверенность → пол 0.5
        (0.80, 0.90),  # принимаемый бренд
        (0.90, 1.00),  # уверенно → 1.0 (и выше — 1.0)
    )


@dataclass(frozen=True)
class ScoringConfig:
    """Настройки нового расчёта заметности (метрика: I=A·P·C, S=ΣI·Δt, V=S·α·β).

    Таблицы наполняются по шагам. Готово: площадь (Шаг 1), положение (Шаг 2),
    контраст (Шаг 3), уверенность (Шаг 5). Заглушка (1.0): значимость (Фаза 2).
    """

    handedness: str = "right"  # правостороннее движение (влияет на сторону в P)
    area: AreaConfig = field(default_factory=AreaConfig)
    position: PositionConfig = field(default_factory=PositionConfig)
    contrast: ContrastConfig = field(default_factory=ContrastConfig)
    confidence: ConfidenceConfig = field(default_factory=ConfidenceConfig)


@dataclass(frozen=True)
class RenderingConfig:
    gap_fill_max_sec: float = 0.35
    save_annotated_frames: bool = False


@dataclass(frozen=True)
class PipelineConfig:
    input_path: Path
    output_dir: Path
    detector_model_path: Path
    classifier_model_path: Path
    run_id: str
    frame_stride: int = DEFAULT_FRAME_STRIDE
    device: str | None = None
    detection: DetectionConfig = field(default_factory=DetectionConfig)
    crop_quality: CropQualityConfig = field(default_factory=CropQualityConfig)
    classification: ClassificationConfig = field(default_factory=ClassificationConfig)
    tracking: TrackingConfig = field(default_factory=TrackingConfig)
    business: BusinessConfig = field(default_factory=BusinessConfig)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    rendering: RenderingConfig = field(default_factory=RenderingConfig)


def default_project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def resolve_project_path(project_root: Path, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return project_root / path
