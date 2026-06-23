from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[4]


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: list[str]) -> list[str]:
    value = os.getenv(name)
    if value is None:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class AppSettings:
    app_name: str = "AI Ad Pipeline API"
    app_version: str = "0.1.0"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    trusted_hosts: list[str] | None = None

    @classmethod
    def from_env(cls) -> AppSettings:
        return cls(
            app_name=os.getenv("AD_PIPELINE_API_NAME", cls.app_name),
            app_version=os.getenv("AD_PIPELINE_API_VERSION", cls.app_version),
            debug=env_bool("AD_PIPELINE_API_DEBUG", cls.debug),
            api_v1_prefix=os.getenv("AD_PIPELINE_API_V1_PREFIX", cls.api_v1_prefix),
            trusted_hosts=env_list("AD_PIPELINE_TRUSTED_HOSTS", ["*"]),
        )


@dataclass(frozen=True)
class CorsSettings:
    allow_origins: list[str]
    allow_credentials: bool
    allow_methods: list[str]
    allow_headers: list[str]

    @classmethod
    def from_env(cls) -> CorsSettings:
        return cls(
            allow_origins=env_list("AD_PIPELINE_CORS_ORIGINS", ["http://localhost:5173", "http://127.0.0.1:5173"]),
            allow_credentials=env_bool("AD_PIPELINE_CORS_CREDENTIALS", True),
            allow_methods=env_list("AD_PIPELINE_CORS_METHODS", ["*"]),
            allow_headers=env_list("AD_PIPELINE_CORS_HEADERS", ["*"]),
        )


@dataclass(frozen=True)
class PipelineOutputSettings:
    project_root: Path
    output_dir: Path

    @classmethod
    def from_env(cls) -> PipelineOutputSettings:
        root = project_root()
        output_dir = Path(os.getenv("AD_PIPELINE_OUTPUT_DIR", str(root / "outputs" / "pipeline"))).resolve()
        return cls(project_root=root, output_dir=output_dir)

