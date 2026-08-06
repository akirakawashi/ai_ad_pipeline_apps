from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from minio.error import S3Error
from sqlalchemy.exc import IntegrityError

from application.exceptions import (
    AssignmentFullError,
    AuthenticationError,
    CatalogImportStateError,
    InactiveUserError,
    PermissionDeniedError,
    SessionExpiredError,
    CatalogNotFoundError,
    DuplicateSlugError,
    GeozoneOverlapError,
    InvalidAssignmentError,
    InvalidCatalogFileError,
    InvalidGeometryError,
    InvalidGeozoneError,
    InvalidPeriodError,
    InvalidUserError,
    InvalidVideoError,
    PipelineRunNotFoundError,
    ProcessingJobStateError,
    UserAlreadyExistsError,
)

# SQLSTATE PostgreSQL: ссылка на несуществующую строку и нарушение уникальности.
FOREIGN_KEY_VIOLATION = "23503"
UNIQUE_VIOLATION = "23505"


def setup_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(SessionExpiredError)
    async def session_expired_handler(
        _: Request,
        __: SessionExpiredError,
    ) -> JSONResponse:
        """401 — сессии нет или её срок вышел; фронт показывает кнопку «Войти».

        `WWW-Authenticate` намеренно не отдаём: заголовок заставил бы браузер
        открыть своё окно ввода пароля, а паролей приложение не спрашивает — вход
        живёт на стороне Keycloak.
        """
        return JSONResponse(
            status_code=401,
            content={"detail": "Нужно войти под доменной учётной записью."},
        )

    @app.exception_handler(PermissionDeniedError)
    async def permission_denied_handler(
        _: Request,
        __: PermissionDeniedError,
    ) -> JSONResponse:
        """403, а не 401: человек вошёл, повторный вход ничего не изменит.

        Названия групп в ответ не попадают — оргструктура компании не должна
        утекать через сообщение об ошибке тому, кому доступ и так закрыт.
        """
        return JSONResponse(
            status_code=403,
            content={"detail": "Недостаточно прав для этого действия."},
        )

    @app.exception_handler(InactiveUserError)
    async def inactive_user_handler(
        _: Request,
        __: InactiveUserError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={"detail": "Учётная запись скрыта в справочнике."},
        )

    @app.exception_handler(AuthenticationError)
    async def authentication_handler(
        _: Request,
        __: AuthenticationError,
    ) -> JSONResponse:
        """502: отказал не запрос, а Keycloak — недоступен либо отверг токен.

        Причина наружу не идёт: в ней бывает и адрес внутреннего сервиса, и
        подробности проверки подписи.
        """
        return JSONResponse(
            status_code=502,
            content={"detail": "Не удалось подтвердить вход через Keycloak."},
        )

    @app.exception_handler(PipelineRunNotFoundError)
    async def run_not_found_handler(
        _: Request,
        exc: PipelineRunNotFoundError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"detail": str(exc)},
        )

    @app.exception_handler(CatalogNotFoundError)
    async def catalog_not_found_handler(
        _: Request,
        exc: CatalogNotFoundError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"detail": str(exc)},
        )

    @app.exception_handler(AssignmentFullError)
    async def assignment_full_handler(
        _: Request,
        exc: AssignmentFullError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"detail": str(exc)},
        )

    @app.exception_handler(UserAlreadyExistsError)
    async def user_exists_handler(
        _: Request,
        exc: UserAlreadyExistsError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"detail": str(exc)},
        )

    @app.exception_handler(InvalidVideoError)
    async def invalid_video_handler(
        _: Request,
        exc: InvalidVideoError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"detail": str(exc)},
        )

    @app.exception_handler(ProcessingJobStateError)
    async def processing_job_state_handler(
        _: Request,
        exc: ProcessingJobStateError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"detail": str(exc)},
        )

    @app.exception_handler(InvalidUserError)
    async def invalid_user_handler(
        _: Request,
        exc: InvalidUserError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"detail": str(exc)},
        )

    @app.exception_handler(InvalidAssignmentError)
    async def invalid_assignment_handler(
        _: Request,
        exc: InvalidAssignmentError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"detail": str(exc)},
        )

    @app.exception_handler(InvalidPeriodError)
    async def invalid_period_handler(
        _: Request,
        exc: InvalidPeriodError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"detail": str(exc)},
        )

    @app.exception_handler(InvalidGeozoneError)
    async def invalid_geozone_handler(
        _: Request,
        exc: InvalidGeozoneError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"detail": str(exc)},
        )

    @app.exception_handler(GeozoneOverlapError)
    async def geozone_overlap_handler(
        _: Request,
        exc: GeozoneOverlapError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"detail": str(exc)},
        )

    @app.exception_handler(InvalidCatalogFileError)
    async def invalid_catalog_file_handler(
        _: Request,
        exc: InvalidCatalogFileError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"detail": str(exc)},
        )

    @app.exception_handler(InvalidGeometryError)
    async def invalid_geometry_handler(
        _: Request,
        exc: InvalidGeometryError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"detail": str(exc)},
        )

    @app.exception_handler(DuplicateSlugError)
    async def duplicate_slug_handler(
        _: Request,
        exc: DuplicateSlugError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"detail": str(exc)},
        )

    @app.exception_handler(CatalogImportStateError)
    async def catalog_import_state_handler(
        _: Request,
        exc: CatalogImportStateError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"detail": str(exc)},
        )

    @app.exception_handler(IntegrityError)
    async def integrity_handler(
        _: Request,
        exc: IntegrityError,
    ) -> JSONResponse:
        """Последний рубеж перед 500 на нарушениях целостности.

        Наружу нельзя отдавать str(exc): SQLAlchemy кладёт туда текст запроса
        и все параметры. Различаем по SQLSTATE — сообщения разные по смыслу.
        """
        sqlstate = getattr(exc.orig, "sqlstate", None)
        if sqlstate == FOREIGN_KEY_VIOLATION:
            return JSONResponse(
                status_code=400,
                content={"detail": "Ссылка на запись, которой не существует."},
            )
        if sqlstate == UNIQUE_VIOLATION:
            return JSONResponse(
                status_code=409,
                content={"detail": "Такая запись уже есть."},
            )
        return JSONResponse(
            status_code=409,
            content={"detail": "Не удалось сохранить: данные противоречат друг другу."},
        )

    @app.exception_handler(S3Error)
    async def object_storage_handler(
        _: Request,
        exc: S3Error,
    ) -> JSONResponse:
        status_code = 404 if exc.code in {"NoSuchKey", "NoSuchBucket"} else 502
        return JSONResponse(
            status_code=status_code,
            content={"detail": "Не удалось получить файл из хранилища."},
        )
