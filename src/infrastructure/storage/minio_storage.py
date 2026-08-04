from __future__ import annotations

from datetime import timedelta

from minio import Minio
from minio.datatypes import Object

from settings.object_storage import ObjectStorageSettings

MINIO_DEFAULT_REGION = "us-east-1"


class MinioStorage:
    def __init__(self, settings: ObjectStorageSettings) -> None:
        self._settings = settings
        self._internal = Minio(
            settings.internal_endpoint,
            access_key=settings.access_key,
            secret_key=settings.secret_key,
            secure=settings.internal_secure,
            region=MINIO_DEFAULT_REGION,
        )
        self._public = Minio(
            settings.public_endpoint,
            access_key=settings.access_key,
            secret_key=settings.secret_key,
            secure=settings.public_secure,
            region=MINIO_DEFAULT_REGION,
        )

    @property
    def bucket(self) -> str:
        return self._settings.bucket

    def ensure_bucket(self) -> None:
        if not self._internal.bucket_exists(self.bucket):
            self._internal.make_bucket(self.bucket)

    def presigned_put(
        self,
        object_key: str,
        *,
        expires_seconds: int | None = None,
    ) -> str:
        return self._public.presigned_put_object(
            self.bucket,
            object_key,
            expires=timedelta(
                seconds=expires_seconds or self._settings.presigned_expiry_seconds
            ),
        )

    def presigned_get(
        self,
        object_key: str,
        *,
        expires_seconds: int | None = None,
    ) -> str:
        return self._public.presigned_get_object(
            self.bucket,
            object_key,
            expires=timedelta(
                seconds=expires_seconds or self._settings.presigned_expiry_seconds
            ),
        )

    def stat(self, object_key: str) -> Object:
        return self._internal.stat_object(self.bucket, object_key)

    def read_bytes(self, object_key: str) -> bytes:
        response = self._internal.get_object(self.bucket, object_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def read_text(self, object_key: str) -> str:
        return self.read_bytes(object_key).decode("utf-8")
