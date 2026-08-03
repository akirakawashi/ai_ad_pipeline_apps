from __future__ import annotations

from fastapi import APIRouter, Depends

from presentation.http.security import require_admin

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/session", status_code=204, dependencies=[Depends(require_admin)])
def check_admin_session() -> None:
    """Проверка пароля и ничего больше: 204 — верный, 401 — нет.

    Нужна, чтобы форма входа спрашивала пароль отдельным запросом, а не
    угадывала его правильность по тому, упал ли первый полезный вызов.
    """
    return None
