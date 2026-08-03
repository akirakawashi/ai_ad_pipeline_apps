from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import defer
from sqlmodel import Session, func, select

from application.common.dto import AdStructureDTO, CatalogImportDTO
from application.exceptions import CatalogImportStateError
from application.interfaces import CityImportTarget
from domain.catalog import CatalogImportStatus, CityBounds, CollapsedPoint, Point
from infrastructure.database.models import AdStructure, CatalogImport, City
from infrastructure.repositories.assignment_mapping import user_ref


# В поле написано «Поиск по адресу», а не «шаблон LIKE»: `%` и `_` там значат
# сами себя. Без этого `%` возвращал весь каталог вместо «ничего не нашлось», а
# «ул_» находило «ул.» — подчёркивание подходило к точке.
LIKE_ESCAPE = "\\"


def _escape_like(value: str) -> str:
    # Слэш первым: иначе следующие две замены заэкранируют слэши, которые сами
    # же и поставили, и `%` превратился бы в литерал обратного слэша с процентом.
    return (
        value.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", f"{LIKE_ESCAPE}%")
        .replace("_", f"{LIKE_ESCAPE}_")
    )


def _bounds(city: City) -> CityBounds | None:
    values = (
        city.bounds_min_latitude,
        city.bounds_max_latitude,
        city.bounds_min_longitude,
        city.bounds_max_longitude,
    )
    if any(value is None for value in values):
        return None
    return CityBounds(*values)  # type: ignore[arg-type]


def _import_to_dto(model: CatalogImport) -> CatalogImportDTO:
    return CatalogImportDTO(
        id=model.catalog_imports_id,
        city_id=model.cities_id,
        revision=model.revision,
        status=CatalogImportStatus(model.status),
        is_current=model.is_current,
        file_names=list(model.file_names or []),
        rows_read=model.rows_read,
        rows_rejected=model.rows_rejected,
        points_total=model.points_total,
        files_rejected=model.files_rejected,
        uploaded_by=user_ref(model.uploaded_by),
        applied_at=model.applied_at,
        created_at=model.created_at,
    )


def _structure_to_dto(model: AdStructure) -> AdStructureDTO:
    return AdStructureDTO(
        id=model.ad_structures_id,
        city_id=model.cities_id,
        address=model.address,
        latitude=model.latitude,
        longitude=model.longitude,
        surfaces_count=model.surfaces_count,
    )


class SqlAdCatalogRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_import_target(self, city_slug: str) -> CityImportTarget | None:
        city = self._city_by_slug(city_slug)
        if city is None:
            return None
        return CityImportTarget(
            city_id=city.cities_id,
            name=city.name,
            bounds=_bounds(city),
        )

    def current_points(self, city_id: str) -> list[Point]:
        rows = self._session.exec(
            select(AdStructure.latitude, AdStructure.longitude)
            .join(
                CatalogImport,
                CatalogImport.catalog_imports_id == AdStructure.catalog_imports_id,
            )
            .where(
                CatalogImport.cities_id == city_id,
                CatalogImport.is_current.is_(True),  # type: ignore[attr-defined]
            )
        ).all()
        return [Point(latitude, longitude) for latitude, longitude in rows]

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
        catalog_import = CatalogImport(
            cities_id=city_id,
            status=CatalogImportStatus.PARSED.value,
            is_current=False,
            file_names=file_names,
            rows_read=rows_read,
            rows_rejected=rows_rejected,
            points_total=len(points),
            files_rejected=files_rejected,
            uploaded_by_users_id=uploaded_by_user_id,
        )
        self._session.add(catalog_import)
        self._session.flush()

        self._session.add_all(
            AdStructure(
                catalog_imports_id=catalog_import.catalog_imports_id,
                cities_id=city_id,
                address=point.address,
                latitude=point.latitude,
                longitude=point.longitude,
                surfaces_count=point.surfaces_count,
                source_rows=point.source_rows,
            )
            for point in points
        )
        self._session.flush()
        self._session.refresh(catalog_import)
        return _import_to_dto(catalog_import)

    def list_imports(self, city_slug: str) -> list[CatalogImportDTO] | None:
        city = self._city_by_slug(city_slug)
        if city is None:
            return None
        models = self._session.exec(
            select(CatalogImport)
            .where(CatalogImport.cities_id == city.cities_id)
            .order_by(CatalogImport.created_at.desc())  # type: ignore[attr-defined]
        ).all()
        return [_import_to_dto(model) for model in models]

    def apply_import(self, import_id: str) -> CatalogImportDTO | None:
        model = self._import_by_id(import_id)
        if model is None:
            return None
        if model.status != CatalogImportStatus.PARSED.value:
            raise CatalogImportStateError(
                "Эта загрузка уже применена или отменена."
            )

        self._lock_city(model.cities_id)
        self._switch_off_current(model.cities_id)

        model.revision = self._next_revision(model.cities_id)
        model.status = CatalogImportStatus.APPLIED.value
        model.is_current = True
        model.applied_at = datetime.now(timezone.utc)
        self._session.add(model)
        self._session.flush()
        self._session.refresh(model)
        return _import_to_dto(model)

    def restore_import(self, import_id: str) -> CatalogImportDTO | None:
        """Откат: прежняя ревизия снова становится текущей.

        Строки не пересоздаются — данные всех ревизий лежат на месте, меняются
        только два флага. Новую ревизию откат не заводит: «сейчас показывается
        ревизия 4» честнее, чем «ревизия 6, копия четвёртой».
        """
        model = self._import_by_id(import_id)
        if model is None:
            return None
        if model.status != CatalogImportStatus.APPLIED.value:
            raise CatalogImportStateError(
                "Откатиться можно только на ранее применённую загрузку."
            )
        if model.is_current:
            raise CatalogImportStateError("Эта ревизия и так показывается сейчас.")

        self._lock_city(model.cities_id)
        self._switch_off_current(model.cities_id)

        model.is_current = True
        self._session.add(model)
        self._session.flush()
        self._session.refresh(model)
        return _import_to_dto(model)

    def hide_import(self, import_id: str) -> CatalogImportDTO | None:
        """Снять ревизию с показа, не назначая другую.

        «У города нет текущей ревизии» — законное состояние: так выглядит город,
        куда ещё ничего не грузили. Без этой ручки единственная ревизия города
        оказывалась несъёмной: откатиться не на что, а удалить текущую запрещено.
        Возврат делается обычным откатом — та же кнопка «Вернуть».
        """
        model = self._import_by_id(import_id)
        if model is None:
            return None
        if not model.is_current:
            raise CatalogImportStateError("Эта ревизия и так не показывается.")

        self._lock_city(model.cities_id)
        model.is_current = False
        self._session.add(model)
        self._session.flush()
        self._session.refresh(model)
        return _import_to_dto(model)

    def delete_import(self, import_id: str) -> bool:
        model = self._import_by_id(import_id)
        if model is None:
            return False
        if model.is_current:
            raise CatalogImportStateError(
                "Нельзя удалить ревизию, которая показывается сейчас."
                " Сначала откатитесь на другую."
            )
        # Конструкции уходят каскадом: у неприменённого пака их всё равно никто
        # не видел, а у старой ревизии это осознанная уборка.
        self._session.delete(model)
        self._session.flush()
        return True

    def list_structures(
        self,
        *,
        city_slug: str,
        search: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[AdStructureDTO], int] | None:
        city = self._city_by_slug(city_slug)
        if city is None:
            return None

        conditions = [
            CatalogImport.cities_id == city.cities_id,
            CatalogImport.is_current.is_(True),  # type: ignore[attr-defined]
        ]
        if search:
            # escape указан явно, хотя у PostgreSQL слэш и так по умолчанию:
            # правильность поиска не должна зависеть от настройки диалекта.
            conditions.append(
                AdStructure.address.ilike(  # type: ignore[attr-defined]
                    f"%{_escape_like(search)}%", escape=LIKE_ESCAPE
                )
            )

        total = self._session.exec(
            select(func.count(AdStructure.ad_structures_id))
            .join(
                CatalogImport,
                CatalogImport.catalog_imports_id == AdStructure.catalog_imports_id,
            )
            .where(*conditions)
        ).one()

        models = self._session.exec(
            select(AdStructure)
            .join(
                CatalogImport,
                CatalogImport.catalog_imports_id == AdStructure.catalog_imports_id,
            )
            .where(*conditions)
            .order_by(AdStructure.address)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()

        return [_structure_to_dto(model) for model in models], int(total)

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()

    # --- вспомогательное -----------------------------------------------------

    def _city_by_slug(self, city_slug: str) -> City | None:
        # defer обязателен: от города здесь нужны только идентификатор, название
        # и рамка, а дорожный слой — это до полутора мегабайт JSONB, которые
        # иначе поднимаются и выбрасываются на каждом чтении каталога.
        return self._session.exec(
            select(City)
            .where(City.slug == city_slug)
            .options(defer(City.roads_geometry))
        ).first()

    def _import_by_id(self, import_id: str) -> CatalogImport | None:
        return self._session.exec(
            select(CatalogImport).where(
                CatalogImport.catalog_imports_id == import_id
            )
        ).first()

    def _lock_city(self, city_id: str) -> None:
        """Блокирует строку города до конца транзакции.

        Иначе два одновременных применения оба погасят текущую ревизию и оба
        зажгут свою — город останется с двумя актуальными.

        defer здесь важнее, чем на чтении: без него дорожный слой едет по сети
        внутри уже взятой блокировки, то есть растягивает критическую секцию
        ради данных, которые этому методу не нужны вовсе.
        """
        self._session.exec(
            select(City)
            .where(City.cities_id == city_id)
            .options(defer(City.roads_geometry))
            .with_for_update()
        ).first()

    def _switch_off_current(self, city_id: str) -> None:
        current = self._session.exec(
            select(CatalogImport).where(
                CatalogImport.cities_id == city_id,
                CatalogImport.is_current.is_(True),  # type: ignore[attr-defined]
            )
        ).all()
        for model in current:
            model.is_current = False
            self._session.add(model)

    def _next_revision(self, city_id: str) -> int:
        highest = self._session.exec(
            select(func.max(CatalogImport.revision)).where(
                CatalogImport.cities_id == city_id
            )
        ).one()
        return int(highest or 0) + 1
