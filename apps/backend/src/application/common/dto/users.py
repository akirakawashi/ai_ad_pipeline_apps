from __future__ import annotations

from datetime import datetime

from application.common.dto.base import ApplicationDTO


class UserDTO(ApplicationDTO):
    """Человек из справочника: постановщик задания или оператор съёмки."""

    id: str
    full_name: str
    is_active: bool = True
    created_at: datetime | None = None
