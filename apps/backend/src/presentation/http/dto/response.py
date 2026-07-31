from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import (
    AliasChoices,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from application.common.dto import (
    AdStructureDTO,
    BrandSummaryDTO,
    CatalogImportDTO,
    CatalogImportReportDTO,
    CityDetailDTO,
    CityDTO,
    RollupBrandDTO,
    RollupTotalsDTO,
    RouteShootingMetricsDTO,
    ShootingMetricsDTO,
    GeozoneDTO,
    OverlayPayloadDTO,
    PaginatedAdStructuresDTO,
    PlaybackDTO,
    RouteDTO,
    AssignmentDTO,
    RunAssignmentRefDTO,
    RunObjectDTO,
    RunSummaryTotalsDTO,
    RunTimelinePointDTO,
    UserDTO,
)
from domain.entities import PipelineRunStage, PipelineRunStatus

T = TypeVar("T")


class ApiModel(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )


class OkResponse(ApiModel, Generic[T]):
    data: T


class UploadTargetResponse(ApiModel):
    method: str
    url: str
    headers: dict[str, str]


class UserResponse(UserDTO):
    pass


class CreateUserRequest(ApiModel):
    full_name: str = Field(min_length=1, max_length=255)


class UpdateUserRequest(ApiModel):
    """Поля со значением None не меняются."""

    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    is_active: bool | None = None


class CreateRunRequest(ApiModel):
    file_name: str = Field(min_length=1, max_length=512)
    content_type: str | None = Field(default=None, max_length=255)
    size_bytes: int = Field(gt=0)
    # Обязательно: съёмка всегда принадлежит заданию, а через него маршруту.
    assignment_id: str = Field(min_length=1, max_length=36)
    # Дата обязательна: это ось графика и серверного фильтра маршрута. Браузер
    # подставляет метку файла, но человек подтверждает или исправляет её.
    shot_started_at: AwareDatetime
    # Оператор общий на всю партию загрузки.
    operator_user_id: str | None = Field(default=None, max_length=36)


class UpdateShootingRequest(ApiModel):
    """PATCH реквизитов съёмки. Ход обработки этим эндпоинтом не меняется."""

    shot_started_at: AwareDatetime | None = None
    operator_user_id: str | None = Field(default=None, max_length=36)

    @field_validator("shot_started_at")
    @classmethod
    def refuse_empty_shooting_date(
        cls,
        value: AwareDatetime | None,
    ) -> AwareDatetime:
        """Поле можно не менять, но очистить обязательную дату нельзя."""
        if value is None:
            raise ValueError("Дата съёмки обязательна.")
        return value

    def changed_fields(self) -> dict[str, object]:
        column_by_field = {"operator_user_id": "operator_users_id"}
        return {
            column_by_field.get(name, name): getattr(self, name)
            for name in self.model_fields_set
        }


class CreateRunResponse(ApiModel):
    run_id: str
    status: PipelineRunStatus
    upload: UploadTargetResponse


class RunAssignmentRefResponse(RunAssignmentRefDTO):
    pass


class RouteResponse(RouteDTO):
    pass


class CreateCityRequest(ApiModel):
    """Новый город. Слаг задаётся один раз: он в URL и его правка ломает ссылки."""

    slug: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    region: str | None = Field(default=None, max_length=255)
    display_order: int = Field(default=0, ge=0)


class UpdateCityRequest(ApiModel):
    """PATCH города: меняются только пришедшие поля. Слага здесь нет намеренно.

    `is_active` — это и есть «скрыть» и «показать». Удаления города нет: у его
    маршрутов каскад на задания и съёмки, и снос города утащил бы всю историю.
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    region: str | None = Field(default=None, max_length=255)
    display_order: int | None = Field(default=None, ge=0)
    is_active: bool | None = Field(default=None)

    def changed_fields(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in self.model_fields_set}


class DrawRouteRequest(ApiModel):
    """Линия маршрута, нарисованная от руки поверх дорожного слоя города.

    Присылается как есть, со всей дрожью руки: точки — пары [долгота, широта] в
    порядке ведения. Класть их на настоящие дороги — работа сервера
    (`domain/route_snapping.py`), и рисующему не нужно попадать в дорогу точно.

    Здесь проверяется только форма — что это вообще список пар чисел. Сколько
    точек нужно и где они должны лежать, решает домен (`parse_stroke`): его
    отказы проходят через обработчики и доходят до человека русской фразой, а
    отказ pydantic вышел бы техническим 422 мимо общей конвенции ответов.

    Единственное исключение — потолок на число точек: тело такого размера не
    надо и разбирать. Непрерывный штрих даже на сорока километрах даёт на
    порядок меньше.
    """

    stroke: list[tuple[float, float]] = Field(max_length=100_000)


class CreateRouteRequest(ApiModel):
    """Новый маршрут. Линия рисуется отдельным запросом, потом."""

    slug: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    color_label: str | None = Field(default=None, max_length=64)
    color_hex: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    description: str | None = Field(default=None, max_length=2000)
    display_order: int = Field(default=0, ge=0)


class UpdateRouteRequest(ApiModel):
    """PATCH маршрута: меняются только пришедшие поля, слаг неизменяем.

    `is_active` — «скрыть» и «показать», как у города. Скрытый маршрут пропадает
    из выбора, его задания и съёмки остаются на месте.
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    color_label: str | None = Field(default=None, max_length=64)
    color_hex: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    description: str | None = Field(default=None, max_length=2000)
    display_order: int | None = Field(default=None, ge=0)
    is_active: bool | None = Field(default=None)

    def changed_fields(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in self.model_fields_set}


class GeozoneResponse(GeozoneDTO):
    pass


class CreateGeozoneRequest(ApiModel):
    """Новый участок значимости. Границы — доли [0,1] от длительности видео."""

    name: str = Field(min_length=1, max_length=255)
    # Описание необязательно: разметка на видео идёт быстро, и заставлять
    # объяснять каждый участок — верный способ получить «ааа» в поле.
    description: str = Field(default="", max_length=2000)
    start_fraction: float = Field(ge=0.0, le=1.0)
    end_fraction: float = Field(ge=0.0, le=1.0)
    coefficient: float = Field(gt=0.0)


class UpdateGeozoneRequest(ApiModel):
    """PATCH участка: меняются только пришедшие поля. Имена колонок совпадают."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    # Пустая строка стирает текст, null запрещён сервисом — как у остальных полей.
    description: str | None = Field(default=None, max_length=2000)
    start_fraction: float | None = Field(default=None, ge=0.0, le=1.0)
    end_fraction: float | None = Field(default=None, ge=0.0, le=1.0)
    coefficient: float | None = Field(default=None, gt=0.0)

    def changed_fields(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in self.model_fields_set}


class AdStructureResponse(AdStructureDTO):
    pass


class PaginatedAdStructuresResponse(PaginatedAdStructuresDTO):
    pass


class CatalogImportResponse(CatalogImportDTO):
    pass


class CatalogImportReportResponse(CatalogImportReportDTO):
    """Отчёт по разобранному паку: что произойдёт, если его применить."""


class CityResponse(CityDTO):
    pass


class CityDetailResponse(CityDetailDTO):
    pass


class AssignmentResponse(AssignmentDTO):
    pass


class CreateAssignmentRequest(ApiModel):
    """Реквизиты задания. Всё необязательно: маршрут и номер и так известны.

    Даты — плановые, их задаёт постановщик. Фактические считаются по съёмкам.
    """

    title: str | None = Field(default=None, max_length=255)
    description: str | None = None
    planned_start_at: AwareDatetime | None = None
    planned_end_at: AwareDatetime | None = None
    author_user_id: str | None = Field(default=None, max_length=36)


class UpdateAssignmentRequest(ApiModel):
    """PATCH: меняются только те поля, что реально пришли в теле.

    Отличить «не прислали» от «прислали null» позволяет model_fields_set —
    иначе описание нельзя было бы очистить.

    `is_active` — «скрыть» и «показать». Тип строгий, без `| None`: колонка
    NOT NULL, и присланный null дошёл бы до базы ошибкой вставки вместо
    внятного 422.
    """

    title: str | None = Field(default=None, max_length=255)
    description: str | None = None
    planned_start_at: AwareDatetime | None = None
    planned_end_at: AwareDatetime | None = None
    author_user_id: str | None = Field(default=None, max_length=36)
    is_active: bool = True

    def changed_fields(self) -> dict[str, object]:
        column_by_field = {"author_user_id": "author_users_id"}
        return {
            column_by_field.get(name, name): getattr(self, name)
            for name in self.model_fields_set
        }


class PaginatedAssignmentsResponse(ApiModel):
    items: list[AssignmentResponse]
    page: int
    page_size: int
    total: int


class RollupTotalsResponse(RollupTotalsDTO):
    pass


class RollupBrandResponse(RollupBrandDTO):
    pass


class ShootingMetricsResponse(ShootingMetricsDTO):
    pass


class RouteShootingMetricsResponse(RouteShootingMetricsDTO):
    pass


class AssignmentSummaryResponse(ApiModel):
    assignment: AssignmentResponse
    totals: RollupTotalsResponse
    brands: list[RollupBrandResponse] = Field(default_factory=list)
    # Сырые метрики съёмок: вход для сравнения съёмок на странице
    # и для любой другой свёртки, если политика поменяется.
    shootings: list[ShootingMetricsResponse] = Field(default_factory=list)


class RouteSummaryResponse(ApiModel):
    """Свёртка маршрута. Форма та же, что у задания, — считается тем же кодом.

    Съёмки идут плоским списком по времени съёмки, у каждой своё задание:
    маршрут показывает каждое видео отдельно, а не средние по кампаниям.
    """

    route: RouteResponse
    assignments_total: int = 0
    totals: RollupTotalsResponse
    brands: list[RollupBrandResponse] = Field(default_factory=list)
    shootings: list[RouteShootingMetricsResponse] = Field(default_factory=list)


class PipelineRunResponse(ApiModel):
    run_id: str = Field(validation_alias=AliasChoices("run_id", "pipeline_runs_id"))
    source_name: str
    source_content_type: str | None
    source_size_bytes: int
    status: PipelineRunStatus
    stage: PipelineRunStage
    progress: int
    status_message: str | None
    error_code: str | None
    error_message: str | None
    fps: float | None
    frame_count: int | None
    frame_stride: int | None
    duration_sec: float | None
    width: int | None
    height: int | None
    created_at: datetime | None
    upload_completed_at: datetime | None
    # Времена обработки. Реквизиты съёмки — ниже, их не путать.
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime | None
    shot_started_at: datetime
    shot_finished_at: datetime | None = None
    assignment: RunAssignmentRefResponse | None = None
    operator: UserResponse | None = None


class PaginatedRunsResponse(ApiModel):
    items: list[PipelineRunResponse]
    page: int
    page_size: int
    total: int


class BrandSummaryResponse(BrandSummaryDTO):
    pass


class RunSummaryTotalsResponse(RunSummaryTotalsDTO):
    pass


class RunSummaryResponse(ApiModel):
    run: PipelineRunResponse
    totals: RunSummaryTotalsResponse
    brands: list[BrandSummaryResponse]


class RunObjectResponse(RunObjectDTO):
    pass


class RunObjectsResponse(ApiModel):
    run_id: str
    objects: list[RunObjectResponse]


class RunTimelinePointResponse(RunTimelinePointDTO):
    pass


class RunTimelineResponse(ApiModel):
    run_id: str
    bucket_seconds: int
    points: list[RunTimelinePointResponse]


class PlaybackResponse(PlaybackDTO):
    pass


class OverlayPayloadResponse(OverlayPayloadDTO):
    pass
