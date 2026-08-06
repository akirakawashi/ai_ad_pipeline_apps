from __future__ import annotations

from pydantic import Field

from settings.base import SettingsModel


class AppSettings(SettingsModel):
    app_name: str = "AI Ad Pipeline API"
    app_version: str = "0.1.0"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    trusted_hosts: list[str] = Field(default_factory=lambda: ["*"])


class CorsSettings(SettingsModel):
    allow_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )
    allow_credentials: bool = True
    allow_methods: list[str] = Field(default_factory=lambda: ["*"])
    allow_headers: list[str] = Field(default_factory=lambda: ["*"])
