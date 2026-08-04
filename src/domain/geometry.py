"""Проверка geojson и рамка города по нему. Чистые функции, без I/O.

Дорожный слой города хранится «как пришёл» — FeatureCollection из OSM без
переработки: его рисует фронтенд, а любая нормализация здесь означала бы вторую
модель геометрии, которую пришлось бы поддерживать наравне с первой. Поэтому его
проверка минимальная и отвечает на один вопрос: это вообще geojson с
координатами в этом мире, или человек загрузил не тот файл.

С линией маршрута иначе, и разница принципиальная. Её больше не загружают
файлом — её рисуют поверх дорожного слоя, а `route_snapping` кладёт нарисованное
на настоящие дороги. Поэтому маршрут приходит сюда уже в одном-единственном
виде: одна упорядоченная ломаная от начала до конца. Из этого вида и собирается
FeatureCollection для хранения — см. `route_line_collection`.
"""

from __future__ import annotations

from collections.abc import Sequence

from domain.catalog import CityBounds

# Больше — почти наверняка не тот файл: дорожный слой Севастополя, самый крупный
# из имеющихся, это 1.5 МБ и ~40 тысяч координат.
MAX_COORDINATES = 2_000_000


class InvalidGeometryError(ValueError):
    """Загруженное не является пригодным FeatureCollection."""


def _walk_coordinates(node: object, found: list[tuple[float, float]]) -> None:
    """Собирает пары [долгота, широта] с любой глубины вложенности.

    Point, LineString, MultiLineString и Polygon отличаются только глубиной
    списков, поэтому спускаемся рекурсивно вместо разбора по типам: нам нужны
    только сами координаты.
    """
    if len(found) > MAX_COORDINATES:
        raise InvalidGeometryError("Слишком много координат в файле.")
    if not isinstance(node, list):
        return
    if (
        len(node) >= 2
        and isinstance(node[0], (int, float))
        and isinstance(node[1], (int, float))
        and not isinstance(node[0], bool)
        and not isinstance(node[1], bool)
    ):
        longitude, latitude = float(node[0]), float(node[1])
        if not (-180.0 <= longitude <= 180.0 and -90.0 <= latitude <= 90.0):
            raise InvalidGeometryError(
                "Координаты выходят за пределы Земли — похоже, файл не в WGS84."
            )
        found.append((longitude, latitude))
        return
    for item in node:
        _walk_coordinates(item, found)


def parse_feature_collection(raw: object) -> dict:
    """Проверяет, что это FeatureCollection с координатами, и отдаёт его как есть.

    Ошибки — с человеческой причиной: файл выбирает человек, и «не тот файл» это
    самый частый исход.
    """
    if not isinstance(raw, dict):
        raise InvalidGeometryError("Файл не содержит объект geojson.")
    if raw.get("type") != "FeatureCollection":
        raise InvalidGeometryError(
            "Ожидается FeatureCollection, а в файле "
            f"«{raw.get('type') or 'ничего похожего'}»."
        )
    features = raw.get("features")
    if not isinstance(features, list) or not features:
        raise InvalidGeometryError("В FeatureCollection нет ни одного объекта.")

    coordinates: list[tuple[float, float]] = []
    for feature in features:
        if not isinstance(feature, dict):
            raise InvalidGeometryError("Среди объектов есть не объект.")
        geometry = feature.get("geometry")
        if isinstance(geometry, dict):
            _walk_coordinates(geometry.get("coordinates"), coordinates)
    if not coordinates:
        raise InvalidGeometryError("Ни у одного объекта нет координат.")
    return raw


def parse_stroke(raw: object) -> list[tuple[float, float]]:
    """Точки нарисованной линии → проверенный список координат.

    Форму (список пар чисел) держит модель запроса; здесь — то, что относится к
    смыслу: точек хотя бы две и все они на этой планете. Проверка та же, что и
    для файла: перепутанные местами широта и долгота дают координату за краем
    мира, и лучше сказать об этом словами, чем строить маршрут по мусору.
    """
    if not isinstance(raw, (list, tuple)):
        raise InvalidGeometryError("Линия не передана.")
    points: list[tuple[float, float]] = []
    for item in raw:
        if (
            not isinstance(item, (list, tuple))
            or len(item) < 2
            or isinstance(item[0], bool)
            or isinstance(item[1], bool)
            or not isinstance(item[0], (int, float))
            or not isinstance(item[1], (int, float))
        ):
            raise InvalidGeometryError("Точка линии должна быть парой чисел.")
        longitude, latitude = float(item[0]), float(item[1])
        if not (-180.0 <= longitude <= 180.0 and -90.0 <= latitude <= 90.0):
            raise InvalidGeometryError("Точка линии выходит за пределы Земли.")
        points.append((longitude, latitude))
    if len(points) < 2:
        raise InvalidGeometryError("В линии должно быть хотя бы две точки.")
    return points


def route_line_collection(path: Sequence[tuple[float, float]]) -> dict:
    """Ломаная маршрута → FeatureCollection ровно с одной линией.

    Одна линия, а не набор кусков, — в этом весь смысл перехода на рисование.
    Пока маршрут грузили файлом из OSM, он был мешком отрезков без порядка, и
    фронтенд раскладывал их эвристикой «ближайший конец от самой западной
    точки». Нарисованный маршрут упорядочен по построению: точки идут так, как
    вела рука, и у маршрута появляются начало, конец и длина.
    """
    if len(path) < 2:
        raise InvalidGeometryError("В маршруте должно быть хотя бы две точки.")
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[point[0], point[1]] for point in path],
                },
            }
        ],
    }


def bounds_of(collection: dict) -> CityBounds | None:
    """Прямоугольник по всем координатам. None — координат не нашлось.

    Этим прямоугольником каталог отсекает точки чужого города, поэтому он
    пересчитывается при каждой заливке дорожного слоя.
    """
    coordinates: list[tuple[float, float]] = []
    for feature in collection.get("features", []):
        if isinstance(feature, dict) and isinstance(feature.get("geometry"), dict):
            _walk_coordinates(feature["geometry"].get("coordinates"), coordinates)
    if not coordinates:
        return None
    longitudes = [point[0] for point in coordinates]
    latitudes = [point[1] for point in coordinates]
    return CityBounds(
        min_latitude=min(latitudes),
        max_latitude=max(latitudes),
        min_longitude=min(longitudes),
        max_longitude=max(longitudes),
    )
