from __future__ import annotations


class PipelineRunNotFoundError(LookupError):
    pass


class InvalidVideoError(ValueError):
    pass


class CatalogNotFoundError(LookupError):
    """Не найден город, маршрут или замер."""


class MeasurementFullError(ValueError):
    """В замере уже MAX_MEASUREMENT_VIDEOS видео."""
