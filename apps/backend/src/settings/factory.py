from __future__ import annotations

from settings.app import (
    AppSettings,
    CorsSettings,
    DatabaseSettings,
    ObjectStorageSettings,
    PipelineSettings,
)


class ConfigFactory:
    def __init__(self) -> None:
        self.app = AppSettings.from_env()
        self.cors = CorsSettings.from_env()
        self.database = DatabaseSettings.from_env()
        self.object_storage = ObjectStorageSettings.from_env()
        self.pipeline = PipelineSettings.from_env()
