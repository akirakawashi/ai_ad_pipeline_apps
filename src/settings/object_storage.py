from __future__ import annotations

from urllib.parse import urlparse

from settings.base import SettingsModel


class ObjectStorageSettings(SettingsModel):
    access_key: str
    secret_key: str
    bucket: str
    internal_endpoint: str
    internal_secure: bool
    public_endpoint: str
    public_secure: bool
    presigned_expiry_seconds: int


def endpoint_parts(value: str) -> tuple[str, bool]:
    parsed = urlparse(value if "://" in value else f"http://{value}")
    if not parsed.netloc:
        raise ValueError(f"Invalid endpoint: {value}")
    return parsed.netloc, parsed.scheme == "https"


def build_object_storage_settings(
    *,
    minio_root_user: str,
    minio_root_password: str,
    minio_bucket: str,
    minio_internal_endpoint: str,
    minio_public_endpoint: str | None,
    minio_presigned_expiry_seconds: int,
) -> ObjectStorageSettings:
    internal_endpoint, internal_secure = endpoint_parts(minio_internal_endpoint)
    public_endpoint, public_secure = endpoint_parts(
        minio_public_endpoint or minio_internal_endpoint
    )
    return ObjectStorageSettings(
        access_key=minio_root_user,
        secret_key=minio_root_password,
        bucket=minio_bucket,
        internal_endpoint=internal_endpoint,
        internal_secure=internal_secure,
        public_endpoint=public_endpoint,
        public_secure=public_secure,
        presigned_expiry_seconds=minio_presigned_expiry_seconds,
    )
