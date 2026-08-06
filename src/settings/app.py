from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from settings.auth import AuthSettings, build_auth_settings
from settings.database import DatabaseSettings, build_database_settings
from settings.http import AppSettings, CorsSettings
from settings.object_storage import (
    ObjectStorageSettings,
    build_object_storage_settings,
)

BACKEND_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ENV_FILE,
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

    processing_service_token: str = Field(
        default="dev-processing-token",
        validation_alias="PROCESSING_SERVICE_TOKEN",
        min_length=16,
    )

    # Реквизиты корпоративного Keycloak. Пусто по умолчанию: он у нас только
    # продовый, адрес и секрет появляются при развёртывании. Нужны, когда
    # AUTH_USE_KEYCLOAK=true; при false не читаются вовсе.
    auth_oidc_issuer: str = Field(
        default="",
        validation_alias="AUTH_OIDC_ISSUER",
    )
    auth_oidc_client_id: str = Field(
        default="",
        validation_alias="AUTH_OIDC_CLIENT_ID",
    )
    auth_oidc_client_secret: str = Field(
        default="",
        validation_alias="AUTH_OIDC_CLIENT_SECRET",
    )
    auth_redirect_uri: str = Field(
        default="http://localhost:8000/api/v1/auth/callback",
        validation_alias="AUTH_REDIRECT_URI",
    )
    auth_frontend_url: str = Field(
        default="http://localhost:5173",
        validation_alias="AUTH_FRONTEND_URL",
    )
    auth_admin_groups: str = Field(
        default="/AI-AD-Admins",
        validation_alias="AUTH_ADMIN_GROUPS",
    )
    auth_claims_dump_path: str = Field(
        default="",
        validation_alias="AUTH_CLAIMS_DUMP_PATH",
    )
    # Переключатель способа входа: true — Keycloak, false — admin/admin.
    # При true реквизиты выше обязаны быть заполнены, иначе запуск падает.
    auth_use_keycloak: bool = Field(
        default=False,
        validation_alias="AUTH_USE_KEYCLOAK",
    )

    app: AppSettings = Field(default_factory=AppSettings)
    cors: CorsSettings = Field(default_factory=CorsSettings)

    @property
    def auth(self) -> AuthSettings:
        return build_auth_settings(
            oidc_issuer=self.auth_oidc_issuer,
            oidc_client_id=self.auth_oidc_client_id,
            oidc_client_secret=self.auth_oidc_client_secret,
            redirect_uri=self.auth_redirect_uri,
            frontend_url=self.auth_frontend_url,
            admin_groups=self.auth_admin_groups,
            claims_dump_path=self.auth_claims_dump_path or None,
            use_keycloak=self.auth_use_keycloak,
        )

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
