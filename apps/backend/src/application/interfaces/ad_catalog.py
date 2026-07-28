from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from application.common.dto import AdStructureDTO, CatalogImportDTO
from domain.catalog import CityBounds, CollapsedPoint, ParseContext, ParsedFile, Point


@dataclass(frozen=True)
class CityImportTarget:
    """Город, в который грузят пак: всё, что нужно разбору и записи."""

    city_id: str
    name: str
    bounds: CityBounds | None


class CatalogFileParser(Protocol):
    """Разбор одного файла каталога. Форматы знает только реализация."""

    def parse(
        self,
        file_name: str,
        content: bytes,
        context: ParseContext,
    ) -> ParsedFile: ...


class AdCatalogRepository(Protocol):
    def get_import_target(self, city_slug: str) -> CityImportTarget | None:
        """None — города нет в справочнике."""
        ...

    def current_points(self, city_id: str) -> list[Point]:
        """Точки актуальной ревизии — для сравнения «было/стало» в отчёте."""
        ...

    def create_import(
        self,
        *,
        city_id: str,
        uploaded_by_user_id: str | None,
        file_names: list[str],
        rows_read: int,
        rows_rejected: int,
        files_rejected: int,
        points: list[CollapsedPoint],
    ) -> CatalogImportDTO:
        """Кладёт разобранный пак неактуальным: до применения его никто не видит."""
        ...

    def get_import(self, import_id: str) -> CatalogImportDTO | None: ...

    def list_imports(self, city_slug: str) -> list[CatalogImportDTO] | None:
        """История ревизий города, свежие сверху. None — города нет."""
        ...

    def apply_import(self, import_id: str) -> CatalogImportDTO | None:
        """Делает пак текущей ревизией города под блокировкой строки города.

        None — пака нет. `CatalogImportStateError`, если он уже применён
        или отменён.
        """
        ...

    def restore_import(self, import_id: str) -> CatalogImportDTO | None:
        """Возвращает город на прежнюю ревизию: гасит текущую, зажигает эту."""
        ...

    def hide_import(self, import_id: str) -> CatalogImportDTO | None:
        """Снимает ревизию с показа, не назначая другую.

        None — пака нет. `CatalogImportStateError`, если он и так не показан.
        """
        ...

    def delete_import(self, import_id: str) -> bool:
        """Удаляет неприменённый пак или старую ревизию. False — пака нет."""
        ...

    def list_structures(
        self,
        *,
        city_slug: str,
        search: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[AdStructureDTO], int] | None:
        """Конструкции текущей ревизии города. None — города нет."""
        ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
