"""Притягивание нарисованного штриха к дорожной сети города.

Человек ведёт мышью по карте линию — приблизительную, с дрожью руки. Здесь она
превращается в маршрут, проложенный **по настоящим дорогам**: одна упорядоченная
ломаная от начала до конца, целиком лежащая на дорожном слое.

Почему это вообще работает: дорожный слой города — не набор независимых линий, а
связный граф. Куски OSM сходятся в перекрёстках общими координатами (85–88 %
концов сегментов совпадают точка-в-точку), и все узлы обоих имеющихся городов
лежат в одной компоненте связности. Значит, между любыми двумя точками сети путь
существует всегда, и «дорогу не нашли» — не тот случай, о котором надо думать.

Алгоритм — классический map matching (Newson & Krupp, HMM + Витерби):

1. Штрих прореживается до равного шага (`resample_step_m`): рука даёт то густо,
   то редко, а решению нужен ровный ход.
2. Для каждой точки берутся несколько ближайших узлов графа — **кандидаты**.
   Один ближайший брать нельзя: у разделённой дороги встречная полоса бывает
   ближе своей, и жадный выбор скачет между ними.
3. Витерби выбирает такую последовательность кандидатов, где мала сумма двух
   штрафов: насколько кандидат далёк от штриха (emission) и насколько путь по
   графу между соседними кандидатами длиннее прямой между точками штриха
   (transition). Второй штраф и есть то, что убивает скачки: перепрыгнуть на
   параллельную улицу и вернуться — это крюк, и он дорого стоит.
4. Выбранные узлы сшиваются кратчайшими путями (A*).

Именно из-за шага 3 расчёт нельзя вести «на лету», пока рука ещё ведёт линию:
решение про каждую точку зависит от того, куда штрих пойдёт дальше. Отсюда и
порядок в интерфейсе — сначала нарисовал целиком, потом «Подтвердить».

Замер на семи реальных маршрутах обоих городов (штрих имитировался плавным
отклонением от эталона — у руки промах низкочастотный, а не пила от точки к
точке):

    промах руки ±20 м  →  ошибка длины ≤0.8 % у шести маршрутов из семи,
                          отклонение от эталона 2–5 м в среднем;
    промах руки ±40 м  →  ошибка длины обычно 2–11 %;
    время               →  12–88 мс на штрих, построение графа ~60 мс на город.

±20 м — это примерно ±2 пикселя на карте города, показанной целиком, то есть
достижимо и без приближения. Остаточная ошибка на больших промахах — это уход на
параллельную улицу или дублёр; сторона проезда продукту безразлична, поэтому
такой уход портит длину, но не смысл маршрута.

Модуль чистый: ни I/O, ни базы, ни HTTP. На вход — geojson дорожного слоя как он
лежит в `cities.roads_geometry`, и точки штриха. На выход — список координат.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Iterable, Sequence

# Координата в том же виде, в каком её хранит geojson: (долгота, широта).
Coordinate = tuple[float, float]

# Метров в градусе широты. Для города (десятки километров) равнопромежуточной
# проекции с этой константой достаточно: ошибка на 20 км — единицы метров, а
# все пороги здесь и так заданы десятками метров.
METERS_PER_DEGREE = 111_320.0

# Округление координаты при склейке узлов: 7 знаков — это ~1 см. Нужно, чтобы
# два конца одной и той же точки, записанные разными кусками OSM, стали одним
# узлом графа. Без склейки граф рассыпается на отдельные линии.
COORDINATE_PRECISION = 7

# Потолок на длину штриха. Рука за один проход столько точек не даёт даже на
# сорока километрах; всё сверх — либо ошибка клиента, либо попытка уронить
# сервер квадратичным разбором.
MAX_STROKE_POINTS = 100_000

# Максимальная длина ребра графа. Смысл — в docstring `from_feature_collection`:
# это условие точности, а не тюнинг производительности.
DEFAULT_MAX_SEGMENT_M = 20.0


class RouteSnappingError(ValueError):
    """Штрих не удалось положить на дорожную сеть."""


@dataclass(frozen=True)
class SnappingConfig:
    """Настройки притягивания. Числа — подобранные, а не выведенные.

    Отобраны перебором по семи реальным маршрутам при промахе руки 20/40/60 м.
    Важный вывод перебора: в разумных пределах эти числа почти не влияют на
    результат — разница между крайними вариантами оказалась меньше разброса
    между маршрутами. Что влияет по-настоящему — дробление рёбер графа
    (см. `RoadGraph.from_feature_collection`). Так что крутить их стоит только
    имея замер на руках, а не по ощущению.
    """

    # Шаг прореживания штриха. Мельче — дороже и без выигрыша в точности:
    # соседние точки начинают попадать в один и тот же узел графа.
    resample_step_m: float = 100.0
    # Радиус поиска кандидатов вокруг точки штриха. Заметно больше типичного
    # промаха руки, иначе на неаккуратном участке кандидатов не окажется вовсе.
    candidate_radius_m: float = 120.0
    # Сколько кандидатов держать на точку. Больше шести не помогает: лишние
    # всё равно проигрывают по обоим штрафам, а цена шага растёт квадратично.
    candidates_per_point: int = 6
    # σ ошибки руки: во сколько раз дорогой промах мимо дороги.
    hand_sigma_m: float = 30.0
    # Масштаб штрафа за крюк. Меньше — сильнее держится прямого хода и хуже
    # проходит настоящие повороты; больше — легче срывается на дублёры.
    detour_scale_m: float = 20.0
    # Насколько далеко искать путь между соседними кандидатами: прямая ×
    # множитель + запас. Реальный объезд квартала в этот предел укладывается,
    # а прогулка через полгорода — уже нет, и такой переход отсекается.
    detour_search_factor: float = 4.0
    detour_search_slack_m: float = 200.0


class RoadGraph:
    """Дорожная сеть города как граф: узлы — координаты, рёбра — куски линий.

    Узлы хранятся индексами, а не кортежами: индекс дешевле в словаре и в куче,
    а исходные координаты нужны только на выходе. Рядом с графом живёт
    пространственная сетка — без неё поиск ближайшего узла превращается в
    перебор восьми тысяч точек на каждую точку штриха.

    Расстояния считаются в метрах в локальной равнопромежуточной проекции с
    началом в первой встреченной координате: для города это точно, а работать с
    метрами в разы понятнее, чем со смесью градусов широты и долготы.
    """

    __slots__ = (
        "_coordinates",
        "_projected",
        "_adjacency",
        "_grid",
        "_cell_size_m",
        "_origin",
    )

    def __init__(
        self,
        coordinates: list[Coordinate],
        projected: list[tuple[float, float]],
        adjacency: list[list[tuple[int, float]]],
        origin: tuple[float, float],
        cell_size_m: float,
    ) -> None:
        self._coordinates = coordinates
        self._projected = projected
        self._adjacency = adjacency
        self._origin = origin
        self._cell_size_m = cell_size_m
        self._grid: dict[tuple[int, int], list[int]] = {}
        for index, (x, y) in enumerate(projected):
            key = (int(x // cell_size_m), int(y // cell_size_m))
            self._grid.setdefault(key, []).append(index)

    @property
    def node_count(self) -> int:
        return len(self._coordinates)

    @classmethod
    def from_feature_collection(
        cls,
        collection: dict,
        *,
        cell_size_m: float = 200.0,
        max_segment_m: float = DEFAULT_MAX_SEGMENT_M,
    ) -> RoadGraph:
        """Строит граф из geojson дорожного слоя.

        Берём только LineString и MultiLineString: точки и полигоны в дорожном
        слое встречаются (площади, развязки-полигоны), но ехать по ним нельзя.

        Длинные рёбра дробятся на куски не длиннее `max_segment_m`. Это не
        оптимизация, а условие работоспособности: маршрут строится по узлам, и
        позиция между двумя узлами непредставима. В исходном слое медиана ребра
        ~22 м, но десятая часть длиннее 80 м, а самые длинные — под полкилометра.
        На таком ребре ближайший к штриху узел оказывается то впереди, то позади
        реального положения, соседние точки штриха выбирают разные концы, и
        сшивание честно прокладывает между ними дорогу туда и обратно. Замер без
        дробления: длина маршрута раздувалась на 24–250 % при любых настройках
        штрафов. Дробление по 20 м удваивает число узлов (8 → 18 тысяч) и стоит
        миллисекунды — цена, которую этот эффект более чем оправдывает.
        """
        lines = list(_iter_line_strings(collection))
        if not lines:
            raise RouteSnappingError(
                "В дорожном слое города нет ни одной линии — по нему нельзя "
                "проложить маршрут."
            )

        indices: dict[Coordinate, int] = {}
        coordinates: list[Coordinate] = []
        projected: list[tuple[float, float]] = []
        adjacency: list[list[tuple[int, float]]] = []
        origin: tuple[float, float] | None = None

        def node(raw: Coordinate) -> int:
            nonlocal origin
            key = (
                round(raw[0], COORDINATE_PRECISION),
                round(raw[1], COORDINATE_PRECISION),
            )
            existing = indices.get(key)
            if existing is not None:
                return existing
            if origin is None:
                origin = key
            index = len(coordinates)
            indices[key] = index
            coordinates.append(key)
            projected.append(_project(key, origin))
            adjacency.append([])
            return index

        def connect(first: int, second: int) -> None:
            weight = _distance(projected[first], projected[second])
            adjacency[first].append((second, weight))
            adjacency[second].append((first, weight))

        for line in lines:
            previous_raw: Coordinate | None = None
            previous: int | None = None
            for raw in line:
                current = node(raw)
                if previous is not None and previous_raw is not None and previous != current:
                    # Промежуточные узлы ставим на прямой между вершинами —
                    # это и есть сама линия дороги, поэтому маршрут остаётся
                    # ровно на ней, а не срезает по хорде.
                    span = _geographic_distance(previous_raw, raw)
                    pieces = max(1, math.ceil(span / max_segment_m))
                    left = previous
                    for step in range(1, pieces):
                        ratio = step / pieces
                        middle = node(
                            (
                                previous_raw[0] + (raw[0] - previous_raw[0]) * ratio,
                                previous_raw[1] + (raw[1] - previous_raw[1]) * ratio,
                            )
                        )
                        if middle != left:
                            connect(left, middle)
                            left = middle
                    if left != current:
                        connect(left, current)
                previous = current
                previous_raw = raw

        if origin is None:  # pragma: no cover — защищено проверкой lines выше
            raise RouteSnappingError("В дорожном слое города нет координат.")
        return cls(coordinates, projected, adjacency, origin, cell_size_m)

    def coordinate(self, index: int) -> Coordinate:
        return self._coordinates[index]

    def neighbours(self, index: int) -> list[tuple[int, float]]:
        """Соседи узла и длины рёбер до них, в метрах."""
        return self._adjacency[index]

    def project(self, point: Coordinate) -> tuple[float, float]:
        return _project(point, self._origin)

    def candidates(self, point: tuple[float, float], radius_m: float, limit: int) -> list[int]:
        """Ближайшие узлы в радиусе, ближний первым. Пусто — дорог рядом нет."""
        rings = max(1, math.ceil(radius_m / self._cell_size_m))
        cell_x = int(point[0] // self._cell_size_m)
        cell_y = int(point[1] // self._cell_size_m)
        found: list[tuple[float, int]] = []
        for dx in range(-rings, rings + 1):
            for dy in range(-rings, rings + 1):
                for index in self._grid.get((cell_x + dx, cell_y + dy), ()):
                    distance = _distance(self._projected[index], point)
                    if distance <= radius_m:
                        found.append((distance, index))
        found.sort()
        return [index for _, index in found[:limit]]

    def shortest_path(self, source: int, target: int) -> list[int] | None:
        """A* по метрической эвристике: прямая между узлами всегда не длиннее пути."""
        if source == target:
            return [source]
        goal = self._projected[target]
        best_known: dict[int, float] = {source: 0.0}
        previous: dict[int, int] = {}
        queue: list[tuple[float, float, int]] = [
            (_distance(self._projected[source], goal), 0.0, source)
        ]
        visited: set[int] = set()
        while queue:
            _, travelled, current = heapq.heappop(queue)
            if current in visited:
                continue
            visited.add(current)
            if current == target:
                break
            for neighbour, weight in self._adjacency[current]:
                candidate = travelled + weight
                if candidate < best_known.get(neighbour, math.inf):
                    best_known[neighbour] = candidate
                    previous[neighbour] = current
                    heapq.heappush(
                        queue,
                        (
                            candidate + _distance(self._projected[neighbour], goal),
                            candidate,
                            neighbour,
                        ),
                    )
        if target not in best_known:
            return None
        path = [target]
        while path[-1] != source:
            path.append(previous[path[-1]])
        path.reverse()
        return path

    def distances_within(self, source: int, limit_m: float) -> dict[int, float]:
        """Дейкстра с потолком: расстояния до всех узлов ближе limit_m.

        Один проход на кандидата вместо пути до каждого кандидата отдельно —
        именно это держит шаг Витерби линейным, а не квадратичным по кандидатам.
        """
        distances: dict[int, float] = {source: 0.0}
        queue: list[tuple[float, int]] = [(0.0, source)]
        visited: set[int] = set()
        while queue:
            travelled, current = heapq.heappop(queue)
            if current in visited or travelled > limit_m:
                continue
            visited.add(current)
            for neighbour, weight in self._adjacency[current]:
                candidate = travelled + weight
                if candidate <= limit_m and candidate < distances.get(neighbour, math.inf):
                    distances[neighbour] = candidate
                    heapq.heappush(queue, (candidate, neighbour))
        return distances


def snap_stroke(
    graph: RoadGraph,
    stroke: Sequence[Coordinate],
    config: SnappingConfig | None = None,
) -> list[Coordinate]:
    """Штрих от руки → упорядоченная ломаная по дорогам города.

    Возвращает координаты в порядке движения — от начала штриха к его концу.
    Направление штриха сохраняется: сторона движения нас не интересует, но
    порядок точек достаётся бесплатно и делает маршрут осью, а не мешком.
    """
    settings = config or SnappingConfig()
    points = _resample(_clean_stroke(stroke), settings.resample_step_m)
    projected = [graph.project(point) for point in points]

    # Точки, рядом с которыми дорог нет вовсе, выбрасываем: рука могла срезать
    # через двор или парк. Дыру потом закроет A* при сшивании — граф связный.
    observations: list[tuple[tuple[float, float], list[int]]] = []
    for point in projected:
        candidates = graph.candidates(
            point,
            settings.candidate_radius_m,
            settings.candidates_per_point,
        )
        if candidates:
            observations.append((point, candidates))

    if not observations:
        raise RouteSnappingError(
            "Линия проходит слишком далеко от дорог города. Ведите её по дорожной сети."
        )
    if len(observations) == 1:
        # Штрих короче шага прореживания: маршрута из одной точки не бывает.
        raise RouteSnappingError("Линия слишком короткая, чтобы проложить по ней маршрут.")

    chosen = _viterbi(graph, observations, settings)
    return _stitch(graph, chosen)


def _viterbi(
    graph: RoadGraph,
    observations: list[tuple[tuple[float, float], list[int]]],
    config: SnappingConfig,
) -> list[int]:
    """Выбор последовательности узлов, наилучшей для штриха целиком.

    Веса логарифмические, поэтому складываются, а не перемножаются. Оба штрафа
    отрицательные, и максимизируется их сумма.
    """
    first_point, first_candidates = observations[0]
    scores: dict[int, float] = {
        candidate: _emission(graph, candidate, first_point, config)
        for candidate in first_candidates
    }
    back_pointers: list[dict[int, int]] = [{}]

    for index in range(1, len(observations)):
        point, candidates = observations[index]
        previous_point, previous_candidates = observations[index - 1]
        straight = _distance(previous_point, point)
        limit = straight * config.detour_search_factor + config.detour_search_slack_m
        reachable = {
            candidate: graph.distances_within(candidate, limit)
            for candidate in previous_candidates
        }

        current: dict[int, float] = {}
        pointers: dict[int, int] = {}
        for candidate in candidates:
            emission = _emission(graph, candidate, point, config)
            best_score = -math.inf
            best_previous: int | None = None
            for previous in previous_candidates:
                travelled = reachable[previous].get(candidate)
                if travelled is None:
                    continue
                transition = -abs(travelled - straight) / config.detour_scale_m
                score = scores[previous] + transition
                if score > best_score:
                    best_score = score
                    best_previous = previous
            if best_previous is None:
                # Ни от одного предшественника сюда не дойти в разумный крюк —
                # цепочка рвётся. Начинаем её заново с этой точки, но с большим
                # штрафом, чтобы разрыв выбирался только когда иного нет.
                best_score = max(scores.values()) - _BREAK_PENALTY
                best_previous = max(scores, key=lambda key: scores[key])
            current[candidate] = best_score + emission
            pointers[candidate] = best_previous
        scores = current
        back_pointers.append(pointers)

    node = max(scores, key=lambda key: scores[key])
    sequence = [node]
    for index in range(len(observations) - 1, 0, -1):
        node = back_pointers[index][node]
        sequence.append(node)
    sequence.reverse()
    return sequence


# Цена разрыва цепочки. Величина условная и работает как «в разы дороже любого
# обычного перехода»: разрыв должен выбираться, только когда связного варианта
# не нашлось совсем.
_BREAK_PENALTY = 1_000.0


def _emission(
    graph: RoadGraph,
    candidate: int,
    point: tuple[float, float],
    config: SnappingConfig,
) -> float:
    """Штраф за то, что узел стоит в стороне от точки штриха (гауссов)."""
    offset = _distance(graph.project(graph.coordinate(candidate)), point)
    return -(offset**2) / (2.0 * config.hand_sigma_m**2)


def _stitch(graph: RoadGraph, nodes: list[int]) -> list[Coordinate]:
    """Выбранные узлы → непрерывная ломаная: между соседями кратчайший путь."""
    unique: list[int] = []
    for node in nodes:
        if not unique or unique[-1] != node:
            unique.append(node)

    path: list[int] = [unique[0]]
    for start, end in zip(unique, unique[1:]):
        segment = graph.shortest_path(start, end)
        if segment is None:
            raise RouteSnappingError(
                "Дорожная сеть города разорвана: между участками линии нет пути."
            )
        path.extend(segment[1:])

    # Возвраты в предыдущий узел намеренно НЕ вычищаем. Маршрут вправе идти
    # туда и обратно: тупиковый отрог, разворот, кольцевой проезд по разным
    # улицам — все четыре маршрута Симферополя устроены именно так. Чистка
    # «петель» выглядела бы уборкой мусора, а срезала бы половину маршрута.
    return [graph.coordinate(index) for index in path]


def _clean_stroke(stroke: Sequence[Coordinate]) -> list[Coordinate]:
    if len(stroke) > MAX_STROKE_POINTS:
        raise RouteSnappingError("В линии слишком много точек.")
    points = [point for point in stroke]
    if len(points) < 2:
        raise RouteSnappingError("Линия должна состоять хотя бы из двух точек.")
    return points


def _resample(points: list[Coordinate], step_m: float) -> list[Coordinate]:
    """Равномерное прореживание по длине: рука ведёт то густо, то редко.

    Считаем пройденное расстояние вдоль всей ломаной и ставим точку каждые
    step_m. Ключевое — доля берётся внутри текущего отрезка (`target` всегда
    лежит между его началом и концом), иначе на длинном отрезке после короткого
    точку выносит за пределы отрезка, и прорежённый штрих начинает вилять
    назад — а Витерби послушно прокладывает по этому вилянию реальный крюк.
    """
    result = [points[0]]
    travelled = 0.0
    target = step_m
    for start, end in zip(points, points[1:]):
        length = _geographic_distance(start, end)
        if length <= 0.0:
            continue
        while travelled + length >= target:
            ratio = (target - travelled) / length
            result.append(
                (
                    start[0] + (end[0] - start[0]) * ratio,
                    start[1] + (end[1] - start[1]) * ratio,
                )
            )
            target += step_m
        travelled += length
    if result[-1] != points[-1]:
        result.append(points[-1])
    return result


def _project(point: Coordinate, origin: tuple[float, float]) -> tuple[float, float]:
    """Градусы → метры от начала координат (равнопромежуточная проекция)."""
    latitude_scale = math.cos(math.radians(origin[1]))
    return (
        (point[0] - origin[0]) * latitude_scale * METERS_PER_DEGREE,
        (point[1] - origin[1]) * METERS_PER_DEGREE,
    )


def _distance(first: tuple[float, float], second: tuple[float, float]) -> float:
    return math.hypot(first[0] - second[0], first[1] - second[1])


def _geographic_distance(first: Coordinate, second: Coordinate) -> float:
    latitude_scale = math.cos(math.radians((first[1] + second[1]) / 2.0))
    return math.hypot(
        (first[0] - second[0]) * latitude_scale * METERS_PER_DEGREE,
        (first[1] - second[1]) * METERS_PER_DEGREE,
    )


def path_length_m(path: Sequence[Coordinate]) -> float:
    """Длина ломаной в метрах. Нужна проверкам и тестам, не самому снапу."""
    return sum(
        _geographic_distance(first, second) for first, second in zip(path, path[1:])
    )


def _iter_line_strings(collection: dict) -> Iterable[list[Coordinate]]:
    for feature in collection.get("features", []):
        if not isinstance(feature, dict):
            continue
        geometry = feature.get("geometry")
        if not isinstance(geometry, dict):
            continue
        kind = geometry.get("type")
        raw = geometry.get("coordinates")
        if kind == "LineString":
            line = _coordinate_list(raw)
            if len(line) >= 2:
                yield line
        elif kind == "MultiLineString" and isinstance(raw, list):
            for part in raw:
                line = _coordinate_list(part)
                if len(line) >= 2:
                    yield line


def _coordinate_list(raw: object) -> list[Coordinate]:
    if not isinstance(raw, list):
        return []
    line: list[Coordinate] = []
    for item in raw:
        if (
            isinstance(item, list)
            and len(item) >= 2
            and isinstance(item[0], (int, float))
            and isinstance(item[1], (int, float))
            and not isinstance(item[0], bool)
            and not isinstance(item[1], bool)
        ):
            line.append((float(item[0]), float(item[1])))
    return line
