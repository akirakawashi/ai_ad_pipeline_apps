from __future__ import annotations

import secrets

from fastapi import Header, HTTPException

from settings.factory import get_settings


def require_processing_service(
    x_processing_token: str | None = Header(default=None),
) -> None:
    expected = get_settings().processing_service_token.encode("utf-8")
    actual = (x_processing_token or "").encode("utf-8")
    if not secrets.compare_digest(actual, expected):
        raise HTTPException(
            status_code=401,
            detail="Неверный токен сервиса обработки.",
        )
