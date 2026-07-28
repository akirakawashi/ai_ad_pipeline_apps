"""Каталог рекламных конструкций: загрузка паков и переключение ревизий.

Пак — это до двадцати файлов на один город. Он сначала только разбирается и
ложится неактуальным: человек смотрит отчёт и решает, применять или нет. До
применения каталог не меняется ни на одну точку.
"""

from __future__ import annotations

from dataclasses import dataclass

from application.common.dto import (
    CatalogImportDTO,
    CatalogImportReportDTO,
    PaginatedAdStructuresDTO,
    RejectedFileDTO,
    RowErrorDTO,
)
from application.exceptions import (
    CatalogImportStateError,
    CatalogNotFoundError,
    InvalidCatalogFileError,
)
from application.interfaces import AdCatalogRepository, CatalogFileParser
from domain.catalog import ParseContext, ParsedFile, collapse_points, compare_points

# Ограничения продукта, а не схемы: правятся здесь, без миграции.
MAX_IMPORT_FILES = 20
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 50 * 1024 * 1024


@dataclass(frozen=True)
class UploadedFile:
    """Файл пака. Байты живут только на время запроса — мы их не сохраняем."""

    name: str
    content: bytes


class AdCatalogService:
    def __init__(
        self,
        repository: AdCatalogRepository,
        parser: CatalogFileParser,
    ) -> None:
        self._repository = repository
        self._parser = parser

    def upload(
        self,
        *,
        city_slug: str,
        uploaded_by_user_id: str | None,
        files: list[UploadedFile],
    ) -> CatalogImportReportDTO:
        self._check_limits(files)

        target = self._repository.get_import_target(city_slug)
        if target is None:
            raise CatalogNotFoundError("Город не найден.")

        context = ParseContext(city_name=target.name, bounds=target.bounds)
        parsed = [
            self._parser.parse(item.name, item.content, context) for item in files
        ]
        accepted = [item for item in parsed if not item.rejected]
        rejected = [item for item in parsed if item.rejected]

        if not accepted:
            raise InvalidCatalogFileError(
                "Ни один файл не подошёл: " + _first_reasons(rejected)
            )

        rows = [row for item in accepted for row in item.rows]
        if not rows:
            # Пустой пак применять нельзя: он стёр бы город целиком, а человек
            # ждёт обновления каталога, а не его исчезновения.
            raise InvalidCatalogFileError(
                "В файлах не нашлось ни одной пригодной строки."
            )

        points = collapse_points(rows)
        before = self._repository.current_points(target.city_id)
        diff = compare_points(before, [point.point for point in points])
        row_errors = [error for item in accepted for error in item.row_errors]

        created = self._repository.create_import(
            city_id=target.city_id,
            uploaded_by_user_id=uploaded_by_user_id,
            file_names=[item.file_name for item in accepted],
            rows_read=len(rows) + len(row_errors),
            rows_rejected=len(row_errors),
            files_rejected=len(rejected),
            points=points,
        )
        self._repository.commit()

        return CatalogImportReportDTO(
            catalog_import=created,
            points_before=len(before),
            points_after=len(points),
            added=diff.added,
            removed=diff.removed,
            collapsed_rows=len(rows) - len(points),
            rejected_files=[
                RejectedFileDTO(file_name=item.file_name, reason=item.rejection or "")
                for item in rejected
            ],
            row_errors=[
                RowErrorDTO(
                    file_name=error.file_name,
                    row_number=error.row_number,
                    reason=error.reason,
                )
                for error in row_errors
            ],
            files_with_extra_sheets=[
                item.file_name for item in accepted if item.extra_sheets
            ],
        )

    def apply(self, import_id: str) -> CatalogImportDTO:
        return self._switch(self._repository.apply_import, import_id)

    def restore(self, import_id: str) -> CatalogImportDTO:
        return self._switch(self._repository.restore_import, import_id)

    def hide(self, import_id: str) -> CatalogImportDTO:
        """Снять с показа. Обратное действие — обычный откат `restore`."""
        return self._switch(self._repository.hide_import, import_id)

    def delete(self, import_id: str) -> None:
        try:
            deleted = self._repository.delete_import(import_id)
        except CatalogImportStateError:
            self._repository.rollback()
            raise
        if not deleted:
            self._repository.rollback()
            raise CatalogNotFoundError("Ревизия не найдена.")
        self._repository.commit()

    def list_imports(self, city_slug: str) -> list[CatalogImportDTO]:
        imports = self._repository.list_imports(city_slug)
        if imports is None:
            raise CatalogNotFoundError("Город не найден.")
        return imports

    def list_structures(
        self,
        *,
        city_slug: str,
        search: str | None,
        page: int,
        page_size: int,
    ) -> PaginatedAdStructuresDTO:
        result = self._repository.list_structures(
            city_slug=city_slug,
            search=search,
            page=page,
            page_size=page_size,
        )
        if result is None:
            raise CatalogNotFoundError("Город не найден.")
        items, total = result
        return PaginatedAdStructuresDTO(
            items=items,
            page=page,
            page_size=page_size,
            total=total,
        )

    def _switch(self, action, import_id: str) -> CatalogImportDTO:
        """Применение и откат отличаются только проверкой состояния в репозитории."""
        try:
            result = action(import_id)
        except CatalogImportStateError:
            self._repository.rollback()
            raise
        if result is None:
            self._repository.rollback()
            raise CatalogNotFoundError("Ревизия не найдена.")
        self._repository.commit()
        return result

    @staticmethod
    def _check_limits(files: list[UploadedFile]) -> None:
        if not files:
            raise InvalidCatalogFileError("Не выбрано ни одного файла.")
        if len(files) > MAX_IMPORT_FILES:
            raise InvalidCatalogFileError(
                f"За раз можно загрузить не более {MAX_IMPORT_FILES} файлов."
            )
        for item in files:
            if len(item.content) > MAX_FILE_BYTES:
                raise InvalidCatalogFileError(
                    f"Файл «{item.name}» больше"
                    f" {MAX_FILE_BYTES // (1024 * 1024)} МБ."
                )
        if sum(len(item.content) for item in files) > MAX_TOTAL_BYTES:
            raise InvalidCatalogFileError(
                f"Суммарный размер файлов больше"
                f" {MAX_TOTAL_BYTES // (1024 * 1024)} МБ."
            )


def _first_reasons(rejected: list[ParsedFile], limit: int = 3) -> str:
    reasons = [
        f"«{item.file_name}» — {item.rejection}" for item in rejected[:limit]
    ]
    tail = "" if len(rejected) <= limit else f" и ещё {len(rejected) - limit}"
    return "; ".join(reasons) + tail
