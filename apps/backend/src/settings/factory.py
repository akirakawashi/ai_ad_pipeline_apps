from __future__ import annotations

from settings.app import AppSettings, CorsSettings, PipelineOutputSettings


class ConfigFactory:
    def __init__(self) -> None:
        self.app = AppSettings.from_env()
        self.cors = CorsSettings.from_env()
        self.pipeline_outputs = PipelineOutputSettings.from_env()

