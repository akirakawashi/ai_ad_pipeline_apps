from __future__ import annotations

import io
import mimetypes
from datetime import timedelta
from pathlib import Path
from typing import BinaryIO

from minio import Minio
from minio.datatypes import Object

from settings.app import ObjectStorageSettings


class MinioStorage:
    def __init__(self, settings: ObjectStorageSettings) -> None:
        self._settings = settings
        self._internal = Minio(
            settings.internal_endpoint,
            access_key=settings.access_key,
            secret_key=settings.secret_key,
            secure=settings.internal_secure,
        )
        self._public = Minio(
            settings.public_endpoint,
            access_key=settings.access_key,
            secret_key=settings.secret_key,
            secure=settings.public_secure,
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
                seconds=expires_seconds
                or self._settings.presigned_expiry_seconds
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
                seconds=expires_seconds
                or self._settings.presigned_expiry_seconds
            ),
        )

    def stat(self, object_key: str) -> Object:
        return self._internal.stat_object(self.bucket, object_key)

    def download_file(self, object_key: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        self._internal.fget_object(
            self.bucket,
            object_key,
            str(destination),
        )

    def upload_file(
        self,
        source: Path,
        object_key: str,
        *,
        content_type: str | None = None,
    ) -> Object:
        resolved_content_type = (
            content_type
            or mimetypes.guess_type(source.name)[0]
            or "application/octet-stream"
        )
        return self._internal.fput_object(
            self.bucket,
            object_key,
            str(source),
            content_type=resolved_content_type,
        )

    def put_stream(
        self,
        object_key: str,
        stream: BinaryIO,
        *,
        length: int,
        content_type: str,
    ) -> Object:
        return self._internal.put_object(
            self.bucket,
            object_key,
            stream,
            length=length,
            content_type=content_type,
        )

    def read_bytes(self, object_key: str) -> bytes:
        response = self._internal.get_object(self.bucket, object_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def read_text(self, object_key: str) -> str:
        return self.read_bytes(object_key).decode("utf-8")

    def put_bytes(
        self,
        object_key: str,
        value: bytes,
        *,
        content_type: str,
    ) -> Object:
        return self.put_stream(
            object_key,
            io.BytesIO(value),
            length=len(value),
            content_type=content_type,
        )
