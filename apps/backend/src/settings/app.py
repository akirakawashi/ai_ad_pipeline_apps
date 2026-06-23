from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote_plus, urlparse

from dotenv import load_dotenv


def project_root() -> Path:
    return Path(__file__).resolve().parents[4]


load_dotenv(project_root() / "apps" / "backend" / ".env")


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value else default


def endpoint_parts(value: str) -> tuple[str, bool]:
    parsed = urlparse(value if "://" in value else f"http://{value}")
    if not parsed.netloc:
        raise ValueError(f"Invalid endpoint: {value}")
    return parsed.netloc, parsed.scheme == "https"


@dataclass(frozen=True)
class AppSettings:
    app_name: str = "AI Ad Pipeline API"
    app_version: str = "0.1.0"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    trusted_hosts: list[str] | None = None

    @classmethod
    def from_env(cls) -> AppSettings:
        return cls(trusted_hosts=["*"])


@dataclass(frozen=True)
class CorsSettings:
    allow_origins: list[str]
    allow_credentials: bool
    allow_methods: list[str]
    allow_headers: list[str]

    @classmethod
    def from_env(cls) -> CorsSettings:
        return cls(
            allow_origins=[
                "http://localhost:5173",
                "http://127.0.0.1:5173",
            ],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )


@dataclass(frozen=True)
class DatabaseSettings:
    url: str

    @classmethod
    def from_env(cls) -> DatabaseSettings:
        user = quote_plus(os.getenv("POSTGRES_USER", "ad_pipeline"))
        password = quote_plus(
            os.getenv("POSTGRES_PASSWORD", "ad_pipeline")
        )
        host = os.getenv("POSTGRES_HOST", "127.0.0.1")
        port = env_int("POSTGRES_PORT", 5432)
        database = quote_plus(os.getenv("POSTGRES_DB", "ad_pipeline"))
        return cls(
            url=(
                f"postgresql+psycopg://{user}:{password}"
                f"@{host}:{port}/{database}"
            )
        )


@dataclass(frozen=True)
class ObjectStorageSettings:
    access_key: str
    secret_key: str
    bucket: str
    internal_endpoint: str
    internal_secure: bool
    public_endpoint: str
    public_secure: bool
    presigned_expiry_seconds: int

    @classmethod
    def from_env(cls) -> ObjectStorageSettings:
        internal_raw = os.getenv(
            "MINIO_INTERNAL_ENDPOINT",
            "http://127.0.0.1:9000",
        )
        public_raw = os.getenv("MINIO_PUBLIC_ENDPOINT", internal_raw)
        internal_endpoint, internal_secure = endpoint_parts(internal_raw)
        public_endpoint, public_secure = endpoint_parts(public_raw)
        return cls(
            access_key=os.getenv("MINIO_ROOT_USER", "ad_pipeline"),
            secret_key=os.getenv(
                "MINIO_ROOT_PASSWORD",
                "ad_pipeline_secret",
            ),
            bucket=os.getenv("MINIO_BUCKET", "ad-pipeline"),
            internal_endpoint=internal_endpoint,
            internal_secure=internal_secure,
            public_endpoint=public_endpoint,
            public_secure=public_secure,
            presigned_expiry_seconds=env_int(
                "MINIO_PRESIGNED_EXPIRY_SECONDS",
                3600,
            ),
        )


@dataclass(frozen=True)
class PipelineSettings:
    project_root: Path
    detector_model_path: Path
    classifier_model_path: Path
    brand_overrides_path: Path | None
    frame_stride: int
    device: str | None
    worker_poll_interval_sec: float
    worker_temp_dir: Path

    @classmethod
    def from_env(cls) -> PipelineSettings:
        root = project_root()
        return cls(
            project_root=root,
            detector_model_path=(
                root / "models/detection/best.pt"
            ).resolve(),
            classifier_model_path=(
                root / "models/classification/best.pt"
            ).resolve(),
            brand_overrides_path=(
                root / "ml/pipeline/brand_overrides.csv"
            ).resolve(),
            frame_stride=1,
            device="0",
            worker_poll_interval_sec=2.0,
            worker_temp_dir=Path("/tmp/ad-pipeline"),
        )
