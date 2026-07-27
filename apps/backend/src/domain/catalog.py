"""Каталог рекламных конструкций: правила без ввода-вывода.

Здесь живёт то, что не зависит ни от формата файла, ни от базы: что считать
одной конструкцией, что считать городом и как сравнить две ревизии между собой.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from math import asin, cos, radians, sin, sqrt
from typing import NamedTuple

EARTH_RADIUS_M = 6_371_000.0

# Порог схлопывания строк в одну конструкцию. В живых файлах строки одной точки
# совпадают посимвольно, так что порог — страховка, а не рабочая лошадь: он
# поглощает округление координат до 5-го знака (≈ 1 м) и мелкие расхождения
# между поставщиками. Ближайшие РАЗНЫЕ точки в присланном файле стоят в 144 м,
# щиты по разные стороны улицы — в 20–40 м, так что до слипания далеко.
MERGE_DISTANCE_M = 10.0

# Порог «та же конструкция» при сравнении двух ревизий. Больше, чем при
# схлопывании: ревизии разделены месяцами и приходят от разных людей, одно и то
# же место у них разъезжается сильнее. Влияет только на текст отчёта.
DIFF_DISTANCE_M = 30.0

# Запас к прямоугольнику города. Прямоугольник строится по дорожному слою и уже
# шире самого города; запас нужен на случай щита у выездной развязки. Задача —
# отсечь случайную точку за десятки километров, а не очертить границу по закону.
CITY_BOUNDS_MARGIN_M = 2_000.0

# Метр в градусах широты — величина постоянная; в градусах долготы зависит от
# широты, поэтому считается на месте.
METERS_PER_LATITUDE_DEGREE = 111_320.0


class CatalogImportStatus(StrEnum):
    PARSED = "parsed"
    APPLIED = "applied"
    CANCELLED = "cancelled"


class Point(NamedTuple):
    latitude: float
    longitude: float


@dataclass(frozen=True)
class SourceRow:
    """Разобранная строка файла: адрес, координата и исходные ячейки целиком.

    `raw` тащим до самой базы, потому что файл после разбора не сохраняется:
    это единственный способ потом ответить, что было в источнике.
    """

    address: str
    latitude: float
    longitude: float
    raw: dict[str, str]

    @property
    def point(self) -> Point:
        return Point(self.latitude, self.longitude)


@dataclass(frozen=True)
class CollapsedPoint:
    """Одна конструкция: точка на карте и сколько строк файла в неё схлопнулось."""

    address: str
    latitude: float
    longitude: float
    surfaces_count: int
    source_rows: list[dict[str, str]]

    @property
    def point(self) -> Point:
        return Point(self.latitude, self.longitude)


@dataclass(frozen=True)
class PointsDiff:
    """Что изменится при переходе на новую ревизию — только для отчёта."""

    added: int
    removed: int
    kept: int


@dataclass(frozen=True)
class RowError:
    """Строка, которую не взяли: где она и почему."""

    file_name: str
    row_number: int
    reason: str


@dataclass(frozen=True)
class ParseContext:
    """Что нужно знать разбору сверх самого файла."""

    city_name: str
    bounds: "CityBounds | None" = None


@dataclass(frozen=True)
class ParsedFile:
    """Итог разбора одного файла.

    `rejection` заполнен, когда файл отвергнут целиком: не открылся, нет шапки
    или в нём чужой город. Строки такого файла не берём вовсе — правило «в паке
    один город» сформулировано как «так не бывает», значит это просто не тот
    файл, и загружать из него половину означало бы молча принять чужую ошибку.
    """

    file_name: str
    rows: list[SourceRow] = field(default_factory=list)
    row_errors: list[RowError] = field(default_factory=list)
    rejection: str | None = None
    extra_sheets: int = 0

    @property
    def rejected(self) -> bool:
        return self.rejection is not None


class CityBounds(NamedTuple):
    """Прямоугольник города по дорожному слою.

    Не граница по закону, а грубая рамка: всё, что далеко за её пределами, —
    точка не этого города и в каталог не попадает.
    """

    min_latitude: float
    max_latitude: float
    min_longitude: float
    max_longitude: float

    def contains(
        self,
        point: Point,
        *,
        margin_m: float = CITY_BOUNDS_MARGIN_M,
    ) -> bool:
        latitude_margin = margin_m / METERS_PER_LATITUDE_DEGREE
        # Долготный градус короче широтного тем сильнее, чем севернее; берём
        # середину прямоугольника, разница внутри города пренебрежима.
        middle_latitude = (self.min_latitude + self.max_latitude) / 2.0
        longitude_scale = max(0.01, cos(radians(middle_latitude)))
        longitude_margin = margin_m / (METERS_PER_LATITUDE_DEGREE * longitude_scale)
        return (
            self.min_latitude - latitude_margin
            <= point.latitude
            <= self.max_latitude + latitude_margin
            and self.min_longitude - longitude_margin
            <= point.longitude
            <= self.max_longitude + longitude_margin
        )


def distance_meters(first: Point, second: Point) -> float:
    """Расстояние по большому кругу. Для городских масштабов точности хватает."""
    latitude_delta = radians(second.latitude - first.latitude)
    longitude_delta = radians(second.longitude - first.longitude)
    haversine = (
        sin(latitude_delta / 2) ** 2
        + cos(radians(first.latitude))
        * cos(radians(second.latitude))
        * sin(longitude_delta / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * asin(sqrt(haversine))


def collapse_points(
    rows: Sequence[SourceRow],
    *,
    merge_distance_m: float = MERGE_DISTANCE_M,
) -> list[CollapsedPoint]:
    """Строки с одной координатой — одна конструкция.

    Так устроен источник: щиты стоят треугольником или друг над другом, и на
    одну координату приходится по восемь-десять строк. Заодно схлопываются
    настоящие дубли между файлами разных людей.

    Кластеризация жадная, вокруг первой встреченной точки: список конструкций
    города — тысячи, а не миллионы, сложности сверх нужного здесь не окупаются.
    """
    anchors: list[Point] = []
    clusters: list[list[SourceRow]] = []

    for row in rows:
        index = _nearest_within(row.point, anchors, merge_distance_m)
        if index is None:
            anchors.append(row.point)
            clusters.append([row])
            continue
        clusters[index].append(row)

    return [
        _collapse_cluster(anchor, cluster)
        for anchor, cluster in zip(anchors, clusters)
    ]


def compare_points(
    previous: Sequence[Point],
    current: Sequence[Point],
    *,
    distance_m: float = DIFF_DISTANCE_M,
) -> PointsDiff:
    """Сколько точек появилось, исчезло и осталось между двумя ревизиями.

    Сопоставляем по близости, а не по адресу: адреса в источнике свободные и
    от поставщика к поставщику пишутся по-разному. Результат идёт только в
    отчёт — в данных ревизии ничем не связаны.
    """
    unmatched = list(previous)
    kept = 0

    for point in current:
        index = _nearest_within(point, unmatched, distance_m)
        if index is None:
            continue
        unmatched.pop(index)
        kept += 1

    return PointsDiff(
        added=len(current) - kept,
        removed=len(unmatched),
        kept=kept,
    )


def _nearest_within(
    point: Point,
    candidates: Sequence[Point],
    max_distance_m: float,
) -> int | None:
    best_index: int | None = None
    best_distance = max_distance_m

    for index, candidate in enumerate(candidates):
        distance = distance_meters(point, candidate)
        if distance <= best_distance:
            best_distance = distance
            best_index = index

    return best_index


def _collapse_cluster(anchor: Point, cluster: Sequence[SourceRow]) -> CollapsedPoint:
    # Координата — первой строки группы, а не среднее: результат не должен
    # зависеть от того, сколько строк доложили и в каком порядке.
    # Адрес — самый частый в группе; при равенстве побеждает встреченный раньше.
    addresses = Counter(row.address for row in cluster)
    return CollapsedPoint(
        address=addresses.most_common(1)[0][0],
        latitude=anchor.latitude,
        longitude=anchor.longitude,
        surfaces_count=len(cluster),
        source_rows=[row.raw for row in cluster],
    )
