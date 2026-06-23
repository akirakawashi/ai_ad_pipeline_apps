from __future__ import annotations

from pathlib import Path
from urllib.parse import quote_plus, urlparse

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def project_root() -> Path:
    return Path(__file__).resolve().parents[4]


def endpoint_parts(value: str) -> tuple[str, bool]:
    parsed = urlparse(value if "://" in value else f"http://{value}")
    if not parsed.netloc:
        raise ValueError(f"Invalid endpoint: {value}")
    return parsed.netloc, parsed.scheme == "https"


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class AppSettings(FrozenModel):
    app_name: str = "AI Ad Pipeline API"
    app_version: str = "0.1.0"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    trusted_hosts: list[str] = Field(default_factory=lambda: ["*"])


class CorsSettings(FrozenModel):
    allow_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )
    allow_credentials: bool = True
    allow_methods: list[str] = Field(default_factory=lambda: ["*"])
    allow_headers: list[str] = Field(default_factory=lambda: ["*"])


class DatabaseSettings(FrozenModel):
    url: str


class ObjectStorageSettings(FrozenModel):
    access_key: str
    secret_key: str
    bucket: str
    internal_endpoint: str
    internal_secure: bool
    public_endpoint: str
    public_secure: bool
    presigned_expiry_seconds: int


class PipelineSettings(FrozenModel):
    project_root: Path = Field(default_factory=project_root)
    detector_model_path: Path = Field(
        default_factory=lambda: (project_root() / "models/detection/best.pt").resolve()
    )
    classifier_model_path: Path = Field(
        default_factory=lambda: (
            project_root() / "models/classification/best.pt"
        ).resolve()
    )
    brand_overrides_path: Path | None = Field(
        default_factory=lambda: (
            project_root() / "ml/pipeline/brand_overrides.csv"
        ).resolve()
    )
    frame_stride: int = Field(default=1, ge=1)
    device: str | None = "0"
    worker_poll_interval_sec: float = Field(default=2.0, gt=0)
    worker_temp_dir: Path = Field(
        default_factory=lambda: project_root() / ".runtime/worker"
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=project_root() / "apps/backend/.env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    postgres_db: str = Field(
        default="ad_pipeline",
        validation_alias="POSTGRES_DB",
    )
    postgres_user: str = Field(
        default="ad_pipeline",
        validation_alias="POSTGRES_USER",
    )
    postgres_password: str = Field(
        default="ad_pipeline",
        validation_alias="POSTGRES_PASSWORD",
    )
    postgres_host: str = Field(
        default="127.0.0.1",
        validation_alias="POSTGRES_HOST",
    )
    postgres_port: int = Field(
        default=5432,
        validation_alias="POSTGRES_PORT",
        ge=1,
        le=65535,
    )

    minio_root_user: str = Field(
        default="ad_pipeline",
        validation_alias="MINIO_ROOT_USER",
    )
    minio_root_password: str = Field(
        default="ad_pipeline_secret",
        validation_alias="MINIO_ROOT_PASSWORD",
    )
    minio_bucket: str = Field(
        default="ad-pipeline",
        validation_alias="MINIO_BUCKET",
    )
    minio_internal_endpoint: str = Field(
        default="http://127.0.0.1:9000",
        validation_alias="MINIO_INTERNAL_ENDPOINT",
    )
    minio_public_endpoint: str | None = Field(
        default=None,
        validation_alias="MINIO_PUBLIC_ENDPOINT",
    )
    minio_presigned_expiry_seconds: int = Field(
        default=3600,
        validation_alias="MINIO_PRESIGNED_EXPIRY_SECONDS",
        gt=0,
    )

    app: AppSettings = Field(default_factory=AppSettings)
    cors: CorsSettings = Field(default_factory=CorsSettings)
    pipeline: PipelineSettings = Field(default_factory=PipelineSettings)

    @property
    def database(self) -> DatabaseSettings:
        user = quote_plus(self.postgres_user)
        password = quote_plus(self.postgres_password)
        database = quote_plus(self.postgres_db)
        return DatabaseSettings(
            url=(
                f"postgresql+psycopg://{user}:{password}"
                f"@{self.postgres_host}:{self.postgres_port}/{database}"
            )
        )

    @property
    def object_storage(self) -> ObjectStorageSettings:
        internal_endpoint, internal_secure = endpoint_parts(
            self.minio_internal_endpoint
        )
        public_endpoint, public_secure = endpoint_parts(
            self.minio_public_endpoint or self.minio_internal_endpoint
        )
        return ObjectStorageSettings(
            access_key=self.minio_root_user,
            secret_key=self.minio_root_password,
            bucket=self.minio_bucket,
            internal_endpoint=internal_endpoint,
            internal_secure=internal_secure,
            public_endpoint=public_endpoint,
            public_secure=public_secure,
            presigned_expiry_seconds=(self.minio_presigned_expiry_seconds),
        )
