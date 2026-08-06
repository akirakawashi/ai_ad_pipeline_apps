from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SettingsModel(BaseModel):
    model_config = ConfigDict(frozen=True)
