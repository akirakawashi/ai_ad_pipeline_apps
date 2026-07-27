from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ApplicationDTO(BaseModel):
    """База всех DTO слоя приложения.

    Живёт отдельным модулем, чтобы pipeline.py, catalog.py и users.py могли
    ссылаться друг на друга без цикла импортов.
    """

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )
