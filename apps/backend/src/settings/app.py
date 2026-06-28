from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from settings.database import DatabaseSettings, build_database_settings
from settings.http import AppSettings, CorsSettings
from settings.object_storage import (
    ObjectStorageSettings,
    build_object_storage_settings,
)
from settings.pipeline import PipelineSettings


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
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
        return build_database_settings(
            postgres_db=self.postgres_db,
            postgres_user=self.postgres_user,
            postgres_password=self.postgres_password,
            postgres_host=self.postgres_host,
            postgres_port=self.postgres_port,
        )

    @property
    def object_storage(self) -> ObjectStorageSettings:
        return build_object_storage_settings(
            minio_root_user=self.minio_root_user,
            minio_root_password=self.minio_root_password,
            minio_bucket=self.minio_bucket,
            minio_internal_endpoint=self.minio_internal_endpoint,
            minio_public_endpoint=self.minio_public_endpoint,
            minio_presigned_expiry_seconds=self.minio_presigned_expiry_seconds,
        )
