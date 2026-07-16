from __future__ import annotations


class PipelineRunNotFoundError(LookupError):
    pass


class InvalidVideoError(ValueError):
    pass


class CatalogNotFoundError(LookupError):
    """Не найден город, маршрут или пачка."""


class BatchFullError(ValueError):
    """В пачке уже MAX_BATCH_VIDEOS видео."""
