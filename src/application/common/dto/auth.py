from __future__ import annotations

from application.common.dto.base import ApplicationDTO


class AuthenticatedUserDTO(ApplicationDTO):
    """Вошедший человек: запись справочника плюс его права.

    `permissions` — снимок последнего входа, посчитанный из групп токена. Он
    здесь, чтобы не считать права заново на каждом запросе, а не потому, что база
    решает доступ: источник правды — группы в токене, и при каждом входе снимок
    перезаписывается.
    """

    id: str
    full_name: str
    username: str | None
    email: str | None
    permissions: list[str]
    is_active: bool = True

    def has(self, permission: str) -> bool:
        return permission in self.permissions
