from __future__ import annotations


class PipelineRunNotFoundError(LookupError):
    pass


class InvalidVideoError(ValueError):
    pass


class ProcessingJobStateError(ValueError):
    """Worker пытается изменить задачу, которая уже не обрабатывается."""


class CatalogNotFoundError(LookupError):
    """Не найден город, маршрут, задание или человек в справочнике."""


class AssignmentFullError(ValueError):
    """В задании уже MAX_ASSIGNMENT_SHOOTINGS видео."""


class InvalidAssignmentError(ValueError):
    """Реквизиты задания противоречивы — например, окончание раньше начала."""


class InvalidPeriodError(ValueError):
    """Период отбора противоречив — конец раньше начала."""


class InvalidUserError(ValueError):
    """ФИО пустое или состоит из одних пробелов."""


class UserAlreadyExistsError(ValueError):
    """Человек с таким ФИО уже есть в справочнике."""


class InvalidGeozoneError(ValueError):
    """Границы участка неверны — вне [0,1] или начало не раньше конца."""


class GeozoneOverlapError(ValueError):
    """Участок пересекается с уже размеченным на этом маршруте."""


class InvalidCatalogFileError(ValueError):
    """Пак не годится: файлов слишком много, они велики или из них нечего взять."""


class CatalogImportStateError(ValueError):
    """Над ревизией нельзя выполнить действие в её нынешнем состоянии.

    Например: применить уже применённую, откатиться на текущую или удалить ту,
    что сейчас показывается.
    """


class DuplicateSlugError(ValueError):
    """Такой слаг уже занят: у города — глобально, у маршрута — внутри города."""


class InvalidGeometryError(ValueError):
    """Загруженный файл не годится как геометрия: не тот формат или не те числа."""
