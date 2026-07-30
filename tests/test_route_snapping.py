"""Притягивание нарисованной линии к дорожной сети.

Проверяется на настоящих данных: дорожные слои Симферополя и Севастополя и семь
маршрутов из сид-миграции. Синтетики тут ровно столько, сколько нужно, чтобы
изобразить руку — сам маршрут и сами дороги подлинные.

Как устроена имитация руки. Берётся эталонный маршрут, и от него откладывается
**плавное** отклонение: шум задаётся редкими узлами (раз в несколько сотен
метров) и интерполируется между ними. Это важнее, чем кажется: если дёргать
каждую точку эталона независимо, получится высокочастотная пила, которой рука
не рисует, и любой честный алгоритм послушно проложит маршрут по её зубцам.
Первый заход этих тестов именно на это и напоролся — числа выглядели провалом
движка, а провалом была модель руки.

±20 м — примерно ±2 пикселя на карте города, показанной целиком, то есть уровень
аккуратности, доступный без приближения.
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

import pytest

from domain.geometry import InvalidGeometryError, route_line_collection
from domain.route_snapping import (
    DEFAULT_MAX_SEGMENT_M,
    RoadGraph,
    RouteSnappingError,
    SnappingConfig,
    path_length_m,
    snap_stroke,
)

GEOMETRY_DIR = (
    Path(__file__).resolve().parents[1]
    / "apps"
    / "backend"
    / "alembic"
    / "seed_data"
    / "geometry"
)

# Сколько маршрутов лежит у каждого города — те же, что заводит сид-миграция.
ROUTES = {"simferopol": 4, "sevastopol": 3}

METERS_PER_DEGREE = 111_320.0


def _load(city: str, name: str) -> dict:
    return json.loads((GEOMETRY_DIR / city / name).read_text(encoding="utf-8"))


def _distance_m(first: tuple[float, float], second: tuple[float, float]) -> float:
    scale = math.cos(math.radians((first[1] + second[1]) / 2.0))
    return math.hypot(
        (first[0] - second[0]) * scale * METERS_PER_DEGREE,
        (first[1] - second[1]) * METERS_PER_DEGREE,
    )


@pytest.fixture(scope="module")
def graphs() -> dict[str, RoadGraph]:
    """Графы обоих городов строятся один раз на модуль: это десятки миллисекунд."""
    return {
        city: RoadGraph.from_feature_collection(_load(city, "export.geojson"))
        for city in ROUTES
    }


def _corridor(city: str, index: int) -> list[tuple[float, float]]:
    """Эталон: маршрут из сида, вытянутый в одну простую ломаную.

    Сами файлы маршрутов — мешки отрезков с ответвлениями (ровно та беда, ради
    которой заводится рисование), поэтому за эталон берём коридор: самый
    удалённый друг от друга пары концов и кратчайший путь между ними.
    """
    features = [
        feature
        for feature in _load(city, f"route_{index}.geojson")["features"]
        if feature.get("geometry", {}).get("type") == "LineString"
    ]
    graph = RoadGraph.from_feature_collection(
        {"type": "FeatureCollection", "features": features},
        # Дробить эталон не нужно: он нужен как линия, а не как сеть для поиска.
        max_segment_m=1_000_000.0,
    )
    far_end = _farthest(graph, 0)
    start = _farthest(graph, far_end)
    path = graph.shortest_path(start, far_end)
    assert path is not None
    return [graph.coordinate(node) for node in path]


def _farthest(graph: RoadGraph, source: int) -> int:
    distances = graph.distances_within(source, math.inf)
    return max(distances, key=lambda node: distances[node])


def _hand(
    points: list[tuple[float, float]],
    sigma_m: float,
    *,
    wobble_m: float = 400.0,
    seed: int = 11,
) -> list[tuple[float, float]]:
    """Эталон + плавное отклонение: так рисует рука, а не генератор шума."""
    generator = random.Random(seed)
    travelled = [0.0]
    for first, second in zip(points, points[1:]):
        travelled.append(travelled[-1] + _distance_m(first, second))
    total = travelled[-1]
    knots = max(2, int(total / wobble_m) + 1)
    offsets_x = [generator.gauss(0, sigma_m) for _ in range(knots + 1)]
    offsets_y = [generator.gauss(0, sigma_m) for _ in range(knots + 1)]

    stroke: list[tuple[float, float]] = []
    for (longitude, latitude), done in zip(points, travelled):
        position = done / total * knots
        index = min(knots - 1, int(position))
        ratio = position - index
        shift_x = offsets_x[index] + (offsets_x[index + 1] - offsets_x[index]) * ratio
        shift_y = offsets_y[index] + (offsets_y[index + 1] - offsets_y[index]) * ratio
        stroke.append(
            (
                longitude + shift_x / (METERS_PER_DEGREE * math.cos(math.radians(latitude))),
                latitude + shift_y / METERS_PER_DEGREE,
            )
        )
    return stroke


def _mean_offset_m(
    path: list[tuple[float, float]],
    reference: list[tuple[float, float]],
) -> float:
    """Среднее расстояние от построенного маршрута до эталона."""
    step = max(1, len(path) // 200)
    offsets = []
    for point in path[::step]:
        offsets.append(min(_distance_m(point, other) for other in reference))
    return sum(offsets) / len(offsets)


CASES = [(city, index) for city, count in ROUTES.items() for index in range(1, count + 1)]


class TestRoadGraph:
    def test_city_network_is_one_connected_whole(self, graphs) -> None:
        """Связность — то, на чём стоит вся затея.

        Если сеть распадается на куски, между двумя точками может не оказаться
        пути, и «нарисуйте иначе» станет обычным ответом вместо исключительного.
        """
        for city, graph in graphs.items():
            reachable = graph.distances_within(0, math.inf)
            assert len(reachable) == graph.node_count, (
                f"дорожная сеть {city} распалась: достижимо "
                f"{len(reachable)} из {graph.node_count} узлов"
            )

    def test_long_edges_are_split(self, graphs) -> None:
        """Дробление рёбер — не оптимизация, а условие точности.

        Без него позиция между двумя далёкими узлами непредставима, соседние
        точки штриха цепляются за разные концы, и маршрут начинает вилять.
        """
        graph = graphs["sevastopol"]
        longest = max(
            (weight for node in range(graph.node_count) for _, weight in graph.neighbours(node)),
            default=0.0,
        )
        assert longest <= DEFAULT_MAX_SEGMENT_M + 0.5

    def test_empty_network_is_refused_with_a_reason(self) -> None:
        with pytest.raises(RouteSnappingError):
            RoadGraph.from_feature_collection({"type": "FeatureCollection", "features": []})


class TestSnapStroke:
    @pytest.mark.parametrize(("city", "index"), CASES)
    def test_careful_hand_recovers_the_route(self, graphs, city, index) -> None:
        """Аккуратно обведённый маршрут восстанавливается почти точно."""
        reference = _corridor(city, index)
        stroke = _hand(reference, sigma_m=20.0)

        path = snap_stroke(graphs[city], stroke)

        reference_length = path_length_m(reference)
        inflation = abs(path_length_m(path) / reference_length - 1.0)
        assert inflation < 0.15, f"длина разошлась с эталоном на {inflation:.0%}"
        assert _mean_offset_m(path, reference) < 25.0

    @pytest.mark.parametrize(("city", "index"), CASES)
    def test_result_is_a_continuous_ordered_line(self, graphs, city, index) -> None:
        """Маршрут — непрерывная ломаная, а не набор кусков.

        Ради этого свойства всё и затевалось: у нарисованного маршрута есть
        начало, конец и порядок, поэтому он годится не только для отрисовки.
        """
        stroke = _hand(_corridor(city, index), sigma_m=20.0)

        path = snap_stroke(graphs[city], stroke)

        assert len(path) >= 2
        gaps = [_distance_m(first, second) for first, second in zip(path, path[1:])]
        assert max(gaps) <= SnappingConfig().resample_step_m, "в маршруте есть разрыв"

    def test_route_follows_real_roads(self, graphs) -> None:
        """Каждая точка построенного маршрута лежит на дорожной сети города."""
        graph = graphs["sevastopol"]
        path = snap_stroke(graph, _hand(_corridor("sevastopol", 1), sigma_m=20.0))

        for point in path[::25]:
            assert graph.candidates(graph.project(point), 0.5, 1), (
                f"точка {point} не лежит на дороге"
            )

    def test_direction_of_the_stroke_is_kept(self, graphs) -> None:
        """Порядок точек идёт от начала штриха к его концу.

        Сторона движения продукту безразлична, но порядок достаётся бесплатно и
        превращает маршрут из мешка отрезков в ось.
        """
        reference = _corridor("sevastopol", 1)
        forward = snap_stroke(graphs["sevastopol"], _hand(reference, sigma_m=20.0))
        backward = snap_stroke(
            graphs["sevastopol"], _hand(list(reversed(reference)), sigma_m=20.0)
        )

        assert _distance_m(forward[0], reference[0]) < 100.0
        assert _distance_m(backward[0], reference[-1]) < 100.0

    def test_stroke_of_one_point_is_refused(self, graphs) -> None:
        with pytest.raises(RouteSnappingError):
            snap_stroke(graphs["simferopol"], [(34.1, 44.95)])

    def test_stroke_far_from_any_road_is_refused(self, graphs) -> None:
        """Линия в чистом поле — это ошибка человека, и сказать надо словами."""
        with pytest.raises(RouteSnappingError):
            snap_stroke(graphs["simferopol"], [(20.0, 20.0), (20.1, 20.1)])


class TestRouteLineCollection:
    def test_builds_a_single_ordered_line(self) -> None:
        collection = route_line_collection([(34.0, 44.9), (34.1, 44.95)])

        assert collection["type"] == "FeatureCollection"
        assert len(collection["features"]) == 1, "маршрут — одна линия, а не мешок"
        geometry = collection["features"][0]["geometry"]
        assert geometry["type"] == "LineString"
        assert geometry["coordinates"] == [[34.0, 44.9], [34.1, 44.95]]

    def test_refuses_a_line_of_one_point(self) -> None:
        with pytest.raises(InvalidGeometryError):
            route_line_collection([(34.0, 44.9)])
