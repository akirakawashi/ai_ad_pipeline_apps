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


class SessionExpiredError(LookupError):
    """Сессии нет или её срок вышел — нужен новый вход.

    Отдельно от «не хватает прав»: это разные ответы браузеру. Истёкшая сессия —
    401 и уход на форму входа, нехватка прав — 403 и объяснение, потому что
    повторный вход тем же человеком ничего не изменит.
    """


class PermissionDeniedError(PermissionError):
    """Человек вошёл, но его группы не дают нужного права."""

    def __init__(self, permission: str) -> None:
        super().__init__(permission)
        self.permission = permission


class InactiveUserError(PermissionError):
    """Человек скрыт в справочнике — ручной запрет работать.

    Проверка домена при этом успешна: учётка в AD жива, а работать в приложении
    ему запретили здесь. Поэтому решение принимается после входа, а не вместо
    него.
    """

    def __init__(self, full_name: str) -> None:
        super().__init__(full_name)
        self.full_name = full_name


class AuthenticationError(RuntimeError):
    """Keycloak не подтвердил вход: код не обменялся или токен не прошёл проверку."""
