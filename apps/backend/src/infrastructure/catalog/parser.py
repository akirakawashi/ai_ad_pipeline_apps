"""Разбор файлов каталога: `.xlsx`, `.xls`, `.csv` → строки со смыслом.

Форматы отличаются только способом достать таблицу; дальше всё идёт одним
путём: ищем шапку, сопоставляем колонки, проверяем каждую строку.

Файлы приходят от разных людей и выглядят по-разному, поэтому разбор терпимый:
шапка не обязана быть первой строкой, колонки узнаются по синонимам, координаты
принимаются и одной ячейкой, и двумя. Всё, что не понято, не выбрасывается —
исходная строка целиком уезжает в `SourceRow.raw`, потому что сам файл мы не
храним.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import openpyxl
import xlrd

from domain.catalog import (
    CityBounds,
    ParseContext,
    ParsedFile,
    Point,
    RowError,
    SourceRow,
)

SUPPORTED_SUFFIXES = {".xlsx", ".xls", ".csv"}

# Шапка бывает не в первой строке: сверху попадаются заголовок и пустые строки.
HEADER_SEARCH_DEPTH = 15

# Кодировки перебираем в порядке убывания вероятности; windows-1251 обязателен —
# русский Excel выгружает CSV именно в нём.
CSV_ENCODINGS = ("utf-8-sig", "utf-8", "windows-1251")
CSV_DELIMITERS = (";", ",", "\t")

CITY_HEADERS = frozenset(
    {"трасса/город", "город", "населенный пункт", "нас пункт", "city"}
)
ADDRESS_HEADERS = frozenset(
    {"адрес", "адрес размещения", "местоположение", "address"}
)
COORDINATES_HEADERS = frozenset({"координаты", "координата", "coordinates", "coords"})
LATITUDE_HEADERS = frozenset({"широта", "lat", "latitude"})
LONGITUDE_HEADERS = frozenset({"долгота", "lon", "lng", "longitude"})

# Городские приставки, которые не должны мешать сравнению названий.
CITY_PREFIXES = ("г.", "г ", "город", "гор.", "пгт", "с.", "п.")


@dataclass(frozen=True)
class _Table:
    rows: list[list[str]]
    extra_sheets: int = 0


@dataclass(frozen=True)
class _Columns:
    address: int
    city: int | None
    coordinates: int | None
    latitude: int | None
    longitude: int | None


class ExcelCatalogParser:
    """Реализация `CatalogFileParser` поверх openpyxl / xlrd / csv."""

    def parse(
        self,
        file_name: str,
        content: bytes,
        context: ParseContext,
    ) -> ParsedFile:
        return parse_file(file_name, content, context)


def parse_file(file_name: str, content: bytes, context: ParseContext) -> ParsedFile:
    suffix = Path(file_name).suffix.casefold()
    if suffix not in SUPPORTED_SUFFIXES:
        return ParsedFile(
            file_name=file_name,
            rejection=f"формат {suffix or 'без расширения'} не поддерживается",
        )

    try:
        table = _read_table(suffix, content)
    except Exception:
        # Библиотеки роняют что угодно на битом файле; наружу нужна одна
        # понятная причина, а не тип исключения из недр openpyxl.
        return ParsedFile(file_name=file_name, rejection="файл не открылся")

    header_index, columns = _find_header(table.rows)
    if columns is None:
        return ParsedFile(
            file_name=file_name,
            rejection="не найдена шапка с адресом и координатами",
            extra_sheets=table.extra_sheets,
        )

    header = table.rows[header_index]
    rows: list[SourceRow] = []
    row_errors: list[RowError] = []

    for offset, cells in enumerate(table.rows[header_index + 1 :], start=1):
        # Номер строки — как в самом Excel, чтобы человек нашёл её глазами.
        row_number = header_index + offset + 1
        if not any(cell for cell in cells):
            continue

        foreign_city = _foreign_city(cells, columns, context.city_name)
        if foreign_city is not None:
            return ParsedFile(
                file_name=file_name,
                rejection=(
                    f"чужой город в строке {row_number}: «{foreign_city}»,"
                    f" ожидался «{context.city_name}»"
                ),
                extra_sheets=table.extra_sheets,
            )

        row, reason = _build_row(cells, header, columns, context)
        if row is None:
            row_errors.append(
                RowError(
                    file_name=file_name,
                    row_number=row_number,
                    reason=reason or "строка не разобрана",
                )
            )
            continue
        rows.append(row)

    return ParsedFile(
        file_name=file_name,
        rows=rows,
        row_errors=row_errors,
        extra_sheets=table.extra_sheets,
    )


def _read_table(suffix: str, content: bytes) -> _Table:
    if suffix == ".xlsx":
        return _read_xlsx(content)
    if suffix == ".xls":
        return _read_xls(content)
    return _read_csv(content)


def _read_xlsx(content: bytes) -> _Table:
    workbook = openpyxl.load_workbook(
        io.BytesIO(content),
        read_only=True,
        data_only=True,
    )
    try:
        sheet = workbook.worksheets[0]
        rows = [
            [_cell_text(value) for value in values]
            for values in sheet.iter_rows(values_only=True)
        ]
        return _Table(rows=rows, extra_sheets=max(0, len(workbook.worksheets) - 1))
    finally:
        workbook.close()


def _read_xls(content: bytes) -> _Table:
    book = xlrd.open_workbook(file_contents=content)
    try:
        sheet = book.sheet_by_index(0)
        rows = [
            [_cell_text(sheet.cell_value(index, column)) for column in range(sheet.ncols)]
            for index in range(sheet.nrows)
        ]
        return _Table(rows=rows, extra_sheets=max(0, book.nsheets - 1))
    finally:
        book.release_resources()


def _read_csv(content: bytes) -> _Table:
    text = _decode_csv(content)
    delimiter = _sniff_delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    return _Table(rows=[[_cell_text(cell) for cell in row] for row in reader])


def _decode_csv(content: bytes) -> str:
    for encoding in CSV_ENCODINGS:
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    # Последний рубеж: лучше разобрать с потерей пары символов, чем отклонить
    # файл целиком из-за одной кривой ячейки.
    return content.decode("utf-8", errors="replace")


def _sniff_delimiter(text: str) -> str:
    """Разделитель — по первой непустой строке.

    Точку с запятой проверяем первой: русский Excel выгружает через неё, а
    координаты внутри ячейки содержат запятую («44.601513, 33.524612») и легко
    сбивают подсчёт в пользу запятой.
    """
    line = next((item for item in text.splitlines() if item.strip()), "")
    counts = {delimiter: line.count(delimiter) for delimiter in CSV_DELIMITERS}
    best = max(CSV_DELIMITERS, key=lambda delimiter: counts[delimiter])
    return best if counts[best] else ","


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        # Excel отдаёт числа как float: 44.601513 не должно превратиться
        # ни в «44.60151300000001», ни в «44.6015130000».
        if value.is_integer():
            return str(int(value))
        return f"{value:.10f}".rstrip("0").rstrip(".")
    if isinstance(value, int):
        return str(value)
    return re.sub(r"\s+", " ", str(value)).strip()


def _normalize_header(value: str) -> str:
    return re.sub(r"[^0-9a-zа-яё/ ]+", "", value.casefold()).strip()


def _find_header(rows: list[list[str]]) -> tuple[int, _Columns | None]:
    for index, cells in enumerate(rows[:HEADER_SEARCH_DEPTH]):
        columns = _match_columns(cells)
        if columns is not None:
            return index, columns
    return 0, None


def _match_columns(cells: list[str]) -> _Columns | None:
    address = city = coordinates = latitude = longitude = None

    for index, cell in enumerate(cells):
        name = _normalize_header(cell)
        if not name:
            continue
        if address is None and name in ADDRESS_HEADERS:
            address = index
        elif city is None and name in CITY_HEADERS:
            city = index
        elif coordinates is None and name in COORDINATES_HEADERS:
            coordinates = index
        elif latitude is None and name in LATITUDE_HEADERS:
            latitude = index
        elif longitude is None and name in LONGITUDE_HEADERS:
            longitude = index

    has_coordinates = coordinates is not None or (
        latitude is not None and longitude is not None
    )
    if address is None or not has_coordinates:
        return None

    return _Columns(
        address=address,
        city=city,
        coordinates=coordinates,
        latitude=latitude,
        longitude=longitude,
    )


def _cell(cells: list[str], index: int | None) -> str:
    if index is None or index >= len(cells):
        return ""
    return cells[index].strip()


def _foreign_city(
    cells: list[str],
    columns: _Columns,
    expected_city: str,
) -> str | None:
    """Название чужого города, если оно в строке есть. Иначе None.

    Пустая ячейка — не ошибка: пак уже объявил город при загрузке.
    """
    value = _cell(cells, columns.city)
    if not value:
        return None
    if _normalize_city(value) == _normalize_city(expected_city):
        return None
    return value


def _normalize_city(value: str) -> str:
    name = re.sub(r"[^0-9a-zа-яё ]+", " ", value.casefold())
    name = re.sub(r"\s+", " ", name).strip()
    for prefix in CITY_PREFIXES:
        cleaned = prefix.strip(". ")
        if name.startswith(f"{cleaned} "):
            name = name[len(cleaned) + 1 :]
            break
    return name.strip()


def _build_row(
    cells: list[str],
    header: list[str],
    columns: _Columns,
    context: ParseContext,
) -> tuple[SourceRow | None, str | None]:
    address = _cell(cells, columns.address)
    if not address:
        return None, "пустой адрес"

    pair = _read_coordinates(cells, columns)
    if pair is None:
        return None, "координаты не разобраны"

    point = _orient(pair, context.bounds)
    if point is None:
        return None, "координаты вне допустимых значений"

    if context.bounds is not None and not context.bounds.contains(point):
        return None, "точка за пределами города"

    return (
        SourceRow(
            address=address,
            latitude=point.latitude,
            longitude=point.longitude,
            raw=_raw_row(cells, header),
        ),
        None,
    )


def _raw_row(cells: list[str], header: list[str]) -> dict[str, str]:
    """Строка целиком, включая колонки, которые разбор не понял."""
    row: dict[str, str] = {}
    for index, cell in enumerate(cells):
        name = header[index].strip() if index < len(header) else ""
        key = name or f"column_{index + 1}"
        if cell:
            row[key] = cell
    return row


def _read_coordinates(
    cells: list[str],
    columns: _Columns,
) -> tuple[float, float] | None:
    if columns.coordinates is not None:
        return _parse_pair(_cell(cells, columns.coordinates))

    first = _parse_number(_cell(cells, columns.latitude))
    second = _parse_number(_cell(cells, columns.longitude))
    if first is None or second is None:
        return None
    return first, second


def _parse_pair(value: str) -> tuple[float, float] | None:
    """Две координаты из одной ячейки: «44.601513, 33.524612».

    Отдельно ловим десятичную запятую («44,601513, 33,524612»): в этом случае
    после разделения по запятой получается четыре куска, а не два.
    """
    if not value:
        return None

    text = value.replace(";", ",").strip()
    chunks = [chunk.strip() for chunk in text.split(",") if chunk.strip()]

    if len(chunks) == 4 and all(chunk.lstrip("-").isdigit() for chunk in chunks):
        first = _parse_number(f"{chunks[0]}.{chunks[1]}")
        second = _parse_number(f"{chunks[2]}.{chunks[3]}")
    elif len(chunks) == 2:
        first = _parse_number(chunks[0])
        second = _parse_number(chunks[1])
    elif len(chunks) == 1:
        parts = chunks[0].split()
        if len(parts) != 2:
            return None
        first = _parse_number(parts[0])
        second = _parse_number(parts[1])
    else:
        return None

    if first is None or second is None:
        return None
    return first, second


def _parse_number(value: str) -> float | None:
    if not value:
        return None
    text = value.replace(",", ".").replace(" ", "")
    try:
        return float(text)
    except ValueError:
        return None


def _orient(pair: tuple[float, float], bounds: CityBounds | None) -> Point | None:
    """Определяет, где широта, а где долгота.

    Порядку в файле не доверяем: поставщики путают колонки местами. Если рамка
    города известна — выбираем тот вариант, который в неё попадает; это надёжнее
    любых догадок по диапазонам. Без рамки считаем, что порядок обычный.
    """
    first, second = pair
    straight = Point(first, second)
    swapped = Point(second, first)

    if bounds is not None:
        if bounds.contains(straight):
            return straight
        if bounds.contains(swapped):
            return swapped

    if not _plausible(straight):
        return swapped if _plausible(swapped) else None
    return straight


def _plausible(point: Point) -> bool:
    return -90.0 <= point.latitude <= 90.0 and -180.0 <= point.longitude <= 180.0
