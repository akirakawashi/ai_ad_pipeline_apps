from __future__ import annotations

import json
import re
from datetime import datetime

from application.common.dto import (
    CityDetailDTO,
    CityDTO,
    GeometryDTO,
    GeozoneDTO,
    ShootingMetricsDTO,
    AssignmentSummaryDTO,
    PaginatedAssignmentsDTO,
    ShootingBrandDTO,
    PipelineRunDTO,
    AssignmentDTO,
    RouteDTO,
    RouteShootingMetricsDTO,
    RouteSummaryDTO,
)
from application.exceptions import (
    CatalogNotFoundError,
    DuplicateSlugError,
    InvalidAssignmentError,
    InvalidGeometryError,
    InvalidGeozoneError,
    InvalidPeriodError,
)
from application.interfaces import CatalogRepository
from application.services.metrics_rollup import rollup_brands, rollup_totals
from application.services.pipeline_run_service import PipelineRunService
from domain.entities import PipelineRunStatus
from domain.geometry import InvalidGeometryError as DomainGeometryError
from domain.geometry import (
    bounds_of,
    parse_feature_collection,
    parse_stroke,
    route_line_collection,
)
from domain.route_snapping import RoadGraph, RouteSnappingError, snap_stroke

# Слаг живёт в URL, поэтому только то, что в URL не портится.
SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")

# Дорожный слой Севастополя — 1.5 МБ, самый крупный из имеющихся. Запас
# четырёхкратный: файл больше почти наверняка не геометрия города.
MAX_GEOMETRY_BYTES = 8 * 1024 * 1024


def _check_slug(slug: str) -> None:
    if not SLUG_PATTERN.match(slug):
        raise InvalidAssignmentError(
            "Слаг — латиница в нижнем регистре, цифры и дефис, от 2 до 64 знаков."
        )


def _parse_geometry(content: bytes) -> dict:
    """Байты файла → проверенный FeatureCollection.

    Ошибки домена переводим в прикладные: домен не знает про HTTP, а причина
    («не тот файл») должна дойти до человека дословно.
    """
    if not content:
        raise InvalidGeometryError("Файл пустой.")
    if len(content) > MAX_GEOMETRY_BYTES:
        raise InvalidGeometryError(
            f"Файл больше {MAX_GEOMETRY_BYTES // (1024 * 1024)} МБ."
        )
    try:
        raw = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InvalidGeometryError(f"Файл не читается как JSON: {error}") from error
    try:
        return parse_feature_collection(raw)
    except DomainGeometryError as error:
        raise InvalidGeometryError(str(error)) from error


def _check_planned_window(start: object, end: object) -> None:
    """Плановое окно не может кончиться раньше, чем началось.

    Обе границы необязательны — постановщик может знать только одну.
    """
    if isinstance(start, datetime) and isinstance(end, datetime) and end < start:
        raise InvalidAssignmentError(
            "Окончание задания не может быть раньше его начала."
        )


def _check_geozone_bounds(start: object, end: object) -> None:
    """Границы участка: 0 ≤ начало < конец ≤ 1.

    Каждое поле по отдельности держит Pydantic (ge/le), здесь — их порядок и
    полнота, в том числе при PATCH одной границы поверх лежащей в базе другой.
    """
    if not (isinstance(start, (int, float)) and isinstance(end, (int, float))):
        raise InvalidGeozoneError("Границы участка не заданы.")
    if not (0.0 <= start < end <= 1.0):
        raise InvalidGeozoneError(
            "Начало участка должно быть строго раньше конца, обе в пределах 0…1."
        )


class CatalogService:
    def __init__(
        self,
        repository: CatalogRepository,
        run_service: PipelineRunService,
    ) -> None:
        # run_service обязателен: сводки задания и маршрута читают метрики съёмок
        # через него, и сервис без него — наполовину нерабочий объект. Раньше
        # параметр был необязательным, и под это в двух методах лежали проверки
        # «создан без run_service»; создавали сервис всё равно всегда одинаково.
        self._repository = repository
        self._run_service = run_service

    def list_cities(self, *, include_inactive: bool = False) -> list[CityDTO]:
        """`include_inactive` включают только справочники на `/admin`.

        Скрытый город обычному пользователю не виден нигде. Показать его надо
        ровно в одном месте — там, где его можно вернуть: удаления города нет,
        и без этого списка скрытый город стал бы недостижимым навсегда.
        """
        return self._repository.list_cities(include_inactive=include_inactive)

    def get_city(
        self,
        city_slug: str,
        *,
        include_inactive: bool = False,
    ) -> CityDetailDTO:
        city = self._repository.get_city(city_slug, include_inactive=include_inactive)
        if city is None:
            raise CatalogNotFoundError("Город не найден.")
        return city

    # --- справочники: города ------------------------------------------------

    def create_city(
        self,
        *,
        slug: str,
        name: str,
        region: str | None,
        display_order: int,
    ) -> CityDTO:
        _check_slug(slug)
        if self._repository.city_slug_taken(slug):
            raise DuplicateSlugError(f"Город со слагом «{slug}» уже есть.")
        city = self._repository.create_city(
            slug=slug,
            name=name,
            region=region,
            display_order=display_order,
        )
        self._repository.commit()
        return city

    def update_city(self, city_slug: str, *, fields: dict[str, object]) -> CityDetailDTO:
        """Слаг в fields не приходит — его нет в модели запроса.

        Причина: слаг лежит в URL, и его правка тихо ломает все сохранённые
        ссылки на город и его маршруты.
        """
        if not self._repository.update_city(city_slug, fields=fields):
            self._repository.rollback()
            raise CatalogNotFoundError("Город не найден.")
        self._repository.commit()
        # Правка города приходит только из справочника, поэтому и ответ полный:
        # скрытые маршруты в нём видны, иначе после скрытия одного из них
        # страница мигала бы исчезнувшей строкой.
        return self.get_city(city_slug, include_inactive=True)

    # --- справочники: маршруты ----------------------------------------------

    def create_route(
        self,
        *,
        city_slug: str,
        slug: str,
        name: str,
        color_label: str | None,
        color_hex: str | None,
        description: str | None,
        display_order: int,
    ) -> RouteDTO:
        _check_slug(slug)
        if self._repository.route_slug_taken(city_slug, slug):
            raise DuplicateSlugError(
                f"Маршрут со слагом «{slug}» в этом городе уже есть."
            )
        route = self._repository.create_route(
            city_slug=city_slug,
            slug=slug,
            name=name,
            color_label=color_label,
            color_hex=color_hex,
            description=description,
            display_order=display_order,
        )
        if route is None:
            self._repository.rollback()
            raise CatalogNotFoundError("Город не найден.")
        self._repository.commit()
        return route

    def update_route(
        self,
        city_slug: str,
        route_slug: str,
        *,
        fields: dict[str, object],
    ) -> RouteDTO:
        if not self._repository.update_route(city_slug, route_slug, fields=fields):
            self._repository.rollback()
            raise CatalogNotFoundError("Маршрут не найден.")
        self._repository.commit()
        # Правка приходит из справочника, и ею же маршрут скрывают: ответ должен
        # вернуться и про скрытый, иначе скрытие выглядело бы как ошибка.
        return self.get_route(city_slug, route_slug, include_inactive=True)

    def get_route(
        self,
        city_slug: str,
        route_slug: str,
        *,
        include_inactive: bool = False,
    ) -> RouteDTO:
        """Скрытый маршрут для продукта не существует — как и скрытый город.

        `include_inactive` поднимают только справочники: им нужно вернуть ответ
        о маршруте, который сами же только что и скрыли.
        """
        route = self._repository.get_route(
            city_slug,
            route_slug,
            include_inactive=include_inactive,
        )
        if route is None:
            raise CatalogNotFoundError("Маршрут не найден.")
        return route

    # --- справочники: геометрия ---------------------------------------------

    def set_roads_geometry(self, city_slug: str, *, content: bytes) -> CityDetailDTO:
        """Дорожный слой города; рамка города пересчитывается здесь же.

        Рамкой каталог отсекает точки чужого города. Слой без пересчитанной
        рамки означал бы, что следующий импорт молча выбросит нормальные точки.
        """
        geometry = _parse_geometry(content)
        if not self._repository.set_roads_geometry(
            city_slug,
            geometry=geometry,
            bounds=bounds_of(geometry),
        ):
            self._repository.rollback()
            raise CatalogNotFoundError("Город не найден.")
        self._repository.commit()
        return self.get_city(city_slug)

    def get_roads_geometry(self, city_slug: str) -> GeometryDTO:
        geometry = self._repository.get_roads_geometry(city_slug)
        if geometry is None:
            raise CatalogNotFoundError("Дорожный слой города не загружен.")
        return geometry

    def draw_route_geometry(
        self,
        city_slug: str,
        route_slug: str,
        *,
        stroke: object,
    ) -> RouteDTO:
        """Нарисованная от руки линия → маршрут по настоящим дорогам города.

        Загрузки geojson для маршрута больше нет: линию рисуют поверх дорожного
        слоя, а `route_snapping` кладёт её на сеть. Причина не в удобстве — так
        маршрут впервые получается **упорядоченной ломаной**. Файл из OSM давал
        мешок отрезков без порядка и с ответвлениями, из которого нельзя было
        взять ни начало, ни длину.

        Дорожный слой города здесь обязателен: рисовать не по чему, если сети
        нет. Это единственное место, где слой читается ради расчёта, а не ради
        отрисовки, — и потому единственное, где его вес (до полутора мегабайт)
        оправдан. Граф строится заново на каждый вызов: ~60 мс на город, а
        рисование маршрута — действие редкое и ручное. Появится нужда — кэш
        ляжет сюда же, не задевая ни домен, ни ручку.
        """
        roads = self._repository.get_roads_geometry(city_slug)
        if roads is None:
            raise InvalidGeometryError(
                "У города не загружен дорожный слой — по нему нечего вести маршрут."
            )
        # Домен не знает про HTTP и говорит своими ошибками; наружу все три
        # причины («точки не те», «сеть пустая», «линия мимо дорог») должны
        # выйти одинаково — как 400 с человеческим текстом.
        try:
            points = parse_stroke(stroke)
            graph = RoadGraph.from_feature_collection(roads.geometry)
            geometry = route_line_collection(snap_stroke(graph, points))
        except (DomainGeometryError, RouteSnappingError) as error:
            raise InvalidGeometryError(str(error)) from error

        if not self._repository.set_route_geometry(
            city_slug,
            route_slug,
            geometry=geometry,
        ):
            self._repository.rollback()
            raise CatalogNotFoundError("Маршрут не найден.")
        self._repository.commit()
        return self.get_route(city_slug, route_slug, include_inactive=True)

    def get_route_geometry(self, city_slug: str, route_slug: str) -> GeometryDTO:
        geometry = self._repository.get_route_geometry(city_slug, route_slug)
        if geometry is None:
            raise CatalogNotFoundError("Геометрия маршрута не загружена.")
        return geometry

    def list_assignments(
        self,
        *,
        city_slug: str,
        route_slug: str,
        page: int,
        page_size: int,
        include_inactive: bool = False,
    ) -> PaginatedAssignmentsDTO:
        # Маршрут тоже смотрим с оглядкой на флаг: в админке задания заводят и на
        # скрытом маршруте — иначе он превратился бы в тупик, где ничего не
        # починить, не показав его сначала всем.
        if (
            self._repository.get_route(
                city_slug, route_slug, include_inactive=include_inactive
            )
            is None
        ):
            raise CatalogNotFoundError("Маршрут не найден.")
        items, total = self._repository.list_assignments(
            city_slug=city_slug,
            route_slug=route_slug,
            page=page,
            page_size=page_size,
            include_inactive=include_inactive,
        )
        return PaginatedAssignmentsDTO(
            items=items,
            page=page,
            page_size=page_size,
            total=total,
        )

    def create_assignment(
        self,
        *,
        city_slug: str,
        route_slug: str,
        title: str | None = None,
        description: str | None = None,
        planned_start_at: datetime | None = None,
        planned_end_at: datetime | None = None,
        author_user_id: str | None = None,
    ) -> AssignmentDTO:
        _check_planned_window(planned_start_at, planned_end_at)
        assignment = self._repository.create_assignment(
            city_slug=city_slug,
            route_slug=route_slug,
            title=title,
            description=description,
            planned_start_at=planned_start_at,
            planned_end_at=planned_end_at,
            author_user_id=author_user_id,
        )
        if assignment is None:
            self._repository.rollback()
            raise CatalogNotFoundError("Маршрут не найден.")
        self._repository.commit()
        return assignment

    def update_assignment(
        self,
        assignment_id: str,
        *,
        fields: dict[str, object],
    ) -> AssignmentDTO:
        """fields содержит только те ключи, которые клиент реально прислал.

        Скрытое задание читаем и правим: этой же ручкой его возвращают обратно
        (`is_active: true`), и 404 на «показать» был бы односторонней дверью.
        """
        current = self._repository.get_assignment(assignment_id, include_inactive=True)
        if current is None:
            raise CatalogNotFoundError("Задание не найдено.")

        # Проверяем окно целиком: клиент мог прислать одну границу, и она
        # должна быть согласована с той, что уже лежит в базе.
        _check_planned_window(
            fields.get("planned_start_at", current.planned_start_at),
            fields.get("planned_end_at", current.planned_end_at),
        )

        assignment = self._repository.update_assignment(assignment_id, fields=fields)
        if assignment is None:
            self._repository.rollback()
            raise CatalogNotFoundError("Задание не найдено.")
        self._repository.commit()
        return assignment

    def get_assignment(
        self,
        assignment_id: str,
        *,
        include_inactive: bool = False,
    ) -> AssignmentDTO:
        assignment = self._repository.get_assignment(
            assignment_id, include_inactive=include_inactive
        )
        if assignment is None:
            raise CatalogNotFoundError("Задание не найдено.")
        return assignment

    def list_assignment_runs(self, assignment_id: str) -> list[PipelineRunDTO]:
        if self._repository.get_assignment(assignment_id) is None:
            raise CatalogNotFoundError("Задание не найдено.")
        return self._repository.list_assignment_runs(assignment_id)

    # --- геозоны ------------------------------------------------------------

    def list_geozones(self, *, city_slug: str, route_slug: str) -> list[GeozoneDTO]:
        geozones = self._repository.list_geozones(city_slug, route_slug)
        if geozones is None:
            raise CatalogNotFoundError("Маршрут не найден.")
        return geozones

    def create_geozone(
        self,
        *,
        city_slug: str,
        route_slug: str,
        name: str,
        description: str,
        start_fraction: float,
        end_fraction: float,
        coefficient: float,
    ) -> GeozoneDTO:
        _check_geozone_bounds(start_fraction, end_fraction)
        geozone = self._repository.create_geozone(
            city_slug=city_slug,
            route_slug=route_slug,
            name=name,
            description=description,
            start_fraction=start_fraction,
            end_fraction=end_fraction,
            coefficient=coefficient,
        )
        if geozone is None:
            self._repository.rollback()
            raise CatalogNotFoundError("Маршрут не найден.")
        self._repository.commit()
        return geozone

    def get_geozone(self, geozone_id: str) -> GeozoneDTO:
        geozone = self._repository.get_geozone(geozone_id)
        if geozone is None:
            raise CatalogNotFoundError("Участок не найден.")
        return geozone

    def update_geozone(
        self,
        geozone_id: str,
        *,
        fields: dict[str, object],
    ) -> GeozoneDTO:
        """fields содержит только присланные ключи; None ни в одном не бывает —
        все поля участка обязательны, очистка запрещена."""
        current = self._repository.get_geozone(geozone_id)
        if current is None:
            raise CatalogNotFoundError("Участок не найден.")
        if any(value is None for value in fields.values()):
            raise InvalidGeozoneError("Поле участка нельзя очистить.")

        # Проверяем границы целиком: клиент мог прислать одну, вторая — из базы.
        _check_geozone_bounds(
            fields.get("start_fraction", current.start_fraction),
            fields.get("end_fraction", current.end_fraction),
        )
        geozone = self._repository.update_geozone(geozone_id, fields=fields)
        if geozone is None:
            self._repository.rollback()
            raise CatalogNotFoundError("Участок не найден.")
        self._repository.commit()
        return geozone

    def delete_geozone(self, geozone_id: str) -> None:
        if not self._repository.delete_geozone(geozone_id):
            self._repository.rollback()
            raise CatalogNotFoundError("Участок не найден.")
        self._repository.commit()

    def get_assignment_summary(self, assignment_id: str) -> AssignmentSummaryDTO:
        """Метрики задания на лету — кэш-таблицы нет, рассинхрона тоже.

        Считаем только по обработанным съёмкам: задание отдаёт цифры по мере
        готовности, а не по принципу «всё или ничего».

        Суммы тут нет намеренно. Объекты в разных съёмках — это разные
        object_id, даже если щит один и тот же физически; сложить их значит
        посчитать один щит столько раз, сколько раз проехали. Меряем
        «сколько видно за съёмку», поэтому усредняем (see metrics_rollup).
        """
        assignment = self._repository.get_assignment(assignment_id)
        if assignment is None:
            raise CatalogNotFoundError("Задание не найдено.")

        runs = self._repository.list_assignment_runs(assignment_id)
        shootings = [
            self._build_shooting(run)
            for run in runs
            if run.status == PipelineRunStatus.COMPLETED
        ]

        return AssignmentSummaryDTO(
            assignment=assignment,
            totals=rollup_totals(shootings, shootings_total=len(runs)),
            brands=rollup_brands(shootings),
            shootings=shootings,
        )

    def get_route_summary(
        self,
        city_slug: str,
        route_slug: str,
        *,
        shot_from: datetime | None = None,
        shot_to: datetime | None = None,
    ) -> RouteSummaryDTO:
        """Метрики маршрута — из съёмок напрямую, не из результатов заданий.

        Задание тут только подпись у съёмки: если усреднять по заданиям, кампания
        из двух проездов весила бы столько же, сколько кампания из двадцати.
        Поэтому единица учёта одна и та же на всех уровнях — одна съёмка.

        Период ничего в этой модели не меняет: он лишь укорачивает список до
        свёртки, а считает по нему та же `metrics_rollup`. Именно поэтому фильтр
        живёт здесь, а не в браузере — вторая реализация правил усреднения
        разошлась бы с первой, и цифра с периодом перестала бы сходиться с
        цифрой без него. По той же причине период не может разрезать задание
        «наполовину»: единица одна, это съёмка, и она либо в окне, либо нет.

        Скрытое задание выпадает отсюда тем же способом и в том же месте — в
        `list_route_runs`, рядом с периодом. Это единственный способ убрать
        проезд из цифр: он требует явного действия человека в админке и
        обратим, потому что «показать» возвращает съёмки в расчёт целиком.

        Цена честности: читаем tracks.csv каждой завершённой съёмки маршрута.
        На десятках терпимо, на сотнях понадобится кэш.
        """
        if shot_from is not None and shot_to is not None and shot_to < shot_from:
            raise InvalidPeriodError(
                "Конец периода не может быть раньше его начала."
            )

        route = self._repository.get_route(city_slug, route_slug)
        if route is None:
            raise CatalogNotFoundError("Маршрут не найден.")

        runs = self._repository.list_route_runs(
            city_slug,
            route_slug,
            shot_from=shot_from,
            shot_to=shot_to,
        )
        if runs is None:
            raise CatalogNotFoundError("Маршрут не найден.")

        shootings = [
            RouteShootingMetricsDTO(
                **self._build_shooting(run).model_dump(),
                # Задание загружено запросом и всегда есть: колонка обязательная,
                # съёмок вне маршрута в системе не бывает.
                assignment=run.assignment,
            )
            for run in runs
            if run.status == PipelineRunStatus.COMPLETED
        ]

        return RouteSummaryDTO(
            route=route,
            # Задания считаем по тем съёмкам, из которых собрана цифра, а не по
            # маршруту целиком: подпись на экране читается «собрано из N заданий
            # · M съёмок», и под периодом «всего заданий на маршруте» сделало бы
            # её неправдой. Заодно честнее и без периода — задание, у которого
            # нет ни одной обработанной съёмки, ни во что не вошло.
            assignments_total=len(
                {item.assignment.assignment_id for item in shootings}
            ),
            totals=rollup_totals(shootings, shootings_total=len(runs)),
            brands=rollup_brands(shootings),
            shootings=shootings,
        )

    def _build_shooting(self, run: PipelineRunDTO) -> ShootingMetricsDTO:
        summary = self._run_service.get_summary(run.run_id)
        return ShootingMetricsDTO(
            run_id=run.run_id,
            source_name=run.source_name,
            shot_started_at=run.shot_started_at,
            duration_sec=run.duration_sec or 0.0,
            objects_count=summary.totals.total_objects,
            brands=[
                ShootingBrandDTO(
                    brand=brand.brand,
                    objects_count=brand.object_count or 0,
                    visibility_index=brand.sum_visibility_value or 0.0,
                )
                for brand in summary.brands
            ],
        )
