from __future__ import annotations


class PipelineRunNotFoundError(LookupError):
    pass


class InvalidVideoError(ValueError):
    pass


class CatalogNotFoundError(LookupError):
    """Не найден город, маршрут, задание или человек в справочнике."""


class AssignmentFullError(ValueError):
    """В задании уже MAX_ASSIGNMENT_SHOOTINGS видео."""


class InvalidAssignmentError(ValueError):
    """Реквизиты задания противоречивы — например, окончание раньше начала."""


class InvalidUserError(ValueError):
    """ФИО пустое или состоит из одних пробелов."""


class UserAlreadyExistsError(ValueError):
    """Человек с таким ФИО уже есть в справочнике."""
