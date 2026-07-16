import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlmodel import Field, Relationship, SQLModel

from domain.entities import PipelineRunStage, PipelineRunStatus


def uuid_string() -> str:
    return str(uuid.uuid4())


class City(SQLModel, table=True):
    __tablename__ = "cities"

    cities_id: str = Field(
        default_factory=uuid_string,
        sa_column=Column(
            String(36),
            primary_key=True,
            default=uuid_string,
            nullable=False,
        ),
    )
    slug: str = Field(
        sa_column=Column(
            String(64),
            unique=True,
            index=True,
            nullable=False,
        ),
    )
    name: str = Field(
        sa_column=Column(String(255), nullable=False),
    )
    region: str | None = Field(
        default=None,
        sa_column=Column(String(255), nullable=True),
    )
    # Путь относительно apps/frontend/public/, без ведущего слэша и домена.
    # Пример: "routes/simferopol/export.geojson". Слэш добавляет фронтенд.
    roads_geojson_path: str | None = Field(
        default=None,
        sa_column=Column(String(512), nullable=True),
    )
    display_order: int = Field(
        default=0,
        sa_column=Column(Integer, default=0, nullable=False),
    )
    is_active: bool = Field(
        default=True,
        sa_column=Column(Boolean, default=True, nullable=False),
    )
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
        ),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False,
        ),
    )

    routes: list["Route"] = Relationship(
        back_populates="city",
        cascade_delete=True,
        sa_relationship_kwargs={
            "order_by": "Route.display_order",
        },
    )


class Route(SQLModel, table=True):
    __tablename__ = "routes"

    routes_id: str = Field(
        default_factory=uuid_string,
        sa_column=Column(
            String(36),
            primary_key=True,
            default=uuid_string,
            nullable=False,
        ),
    )
    cities_id: str = Field(
        sa_column=Column(
            String(36),
            ForeignKey(
                "cities.cities_id",
                ondelete="CASCADE",
            ),
            index=True,
            nullable=False,
        ),
    )
    slug: str = Field(
        sa_column=Column(String(64), nullable=False),
    )
    name: str = Field(
        sa_column=Column(String(255), nullable=False),
    )
    color_label: str | None = Field(
        default=None,
        sa_column=Column(String(64), nullable=True),
    )
    color_hex: str | None = Field(
        default=None,
        sa_column=Column(String(16), nullable=True),
    )
    # Полный путь относительно apps/frontend/public/, без ведущего слэша.
    # Пример: "routes/simferopol/route_1.geojson".
    geojson_path: str = Field(
        sa_column=Column(String(512), nullable=False),
    )
    display_order: int = Field(
        default=0,
        sa_column=Column(Integer, default=0, nullable=False),
    )
    is_active: bool = Field(
        default=True,
        sa_column=Column(Boolean, default=True, nullable=False),
    )
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
        ),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False,
        ),
    )

    city: City | None = Relationship(back_populates="routes")
    batches: list["RouteBatch"] = Relationship(
        back_populates="route",
        cascade_delete=True,
        sa_relationship_kwargs={
            "order_by": "RouteBatch.sequence_number",
        },
    )

    __table_args__ = (
        UniqueConstraint(
            "cities_id",
            "slug",
            name="uq_routes_city_slug",
        ),
    )


class RouteBatch(SQLModel, table=True):
    __tablename__ = "route_batches"

    route_batches_id: str = Field(
        default_factory=uuid_string,
        sa_column=Column(
            String(36),
            primary_key=True,
            default=uuid_string,
            nullable=False,
        ),
    )
    routes_id: str = Field(
        sa_column=Column(
            String(36),
            ForeignKey(
                "routes.routes_id",
                ondelete="CASCADE",
            ),
            index=True,
            nullable=False,
        ),
    )
    sequence_number: int = Field(
        sa_column=Column(Integer, nullable=False),
    )
    # NULL означает "вычислять": «Пачка №{sequence_number} · {created_at}».
    title: str | None = Field(
        default=None,
        sa_column=Column(String(255), nullable=True),
    )
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
            index=True,
        ),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False,
        ),
    )

    route: Route | None = Relationship(back_populates="batches")
    runs: list["PipelineRun"] = Relationship(back_populates="batch")

    __table_args__ = (
        UniqueConstraint(
            "routes_id",
            "sequence_number",
            name="uq_route_batches_route_sequence",
        ),
    )


class PipelineRun(SQLModel, table=True):
    __tablename__ = "pipeline_runs"

    pipeline_runs_id: str = Field(
        default_factory=uuid_string,
        sa_column=Column(
            String(36),
            primary_key=True,
            default=uuid_string,
            nullable=False,
        ),
    )
    source_name: str = Field(
        sa_column=Column(String(512), nullable=False),
    )
    source_object_key: str = Field(
        sa_column=Column(
            String(1024),
            unique=True,
            nullable=False,
        ),
    )
    source_content_type: str | None = Field(
        default=None,
        sa_column=Column(String(255), nullable=True),
    )
    source_size_bytes: int = Field(
        default=0,
        sa_column=Column(
            BigInteger,
            default=0,
            nullable=False,
        ),
    )

    # NULL означает «Без маршрута» — разовая загрузка вне города и маршрута.
    route_batches_id: str | None = Field(
        default=None,
        sa_column=Column(
            String(36),
            ForeignKey(
                "route_batches.route_batches_id",
                ondelete="SET NULL",
            ),
            index=True,
            nullable=True,
        ),
    )

    status: str = Field(
        default=PipelineRunStatus.UPLOADING.value,
        sa_column=Column(
            String(32),
            default=PipelineRunStatus.UPLOADING.value,
            index=True,
            nullable=False,
        ),
    )
    stage: str = Field(
        default=PipelineRunStage.UPLOAD.value,
        sa_column=Column(
            String(64),
            default=PipelineRunStage.UPLOAD.value,
            nullable=False,
        ),
    )
    progress: int = Field(
        default=0,
        ge=0,
        le=100,
        sa_column=Column(
            Integer,
            default=0,
            nullable=False,
        ),
    )
    status_message: str | None = Field(
        default=None,
        sa_column=Column(String(1024), nullable=True),
    )
    error_code: str | None = Field(
        default=None,
        sa_column=Column(String(128), nullable=True),
    )
    error_message: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )

    fps: float | None = Field(
        default=None,
        sa_column=Column(Float, nullable=True),
    )
    frame_count: int | None = Field(
        default=None,
        sa_column=Column(Integer, nullable=True),
    )
    frame_stride: int | None = Field(
        default=None,
        sa_column=Column(Integer, nullable=True),
    )
    duration_sec: float | None = Field(
        default=None,
        sa_column=Column(Float, nullable=True),
    )
    width: int | None = Field(
        default=None,
        sa_column=Column(Integer, nullable=True),
    )
    height: int | None = Field(
        default=None,
        sa_column=Column(Integer, nullable=True),
    )

    worker_id: str | None = Field(
        default=None,
        sa_column=Column(
            String(255),
            index=True,
            nullable=True,
        ),
    )
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
            index=True,
        ),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False,
        ),
    )
    upload_completed_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=True,
        ),
    )
    started_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=True,
        ),
    )
    completed_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            nullable=True,
        ),
    )

    batch: RouteBatch | None = Relationship(back_populates="runs")
    artifacts: list["PipelineArtifact"] = Relationship(
        back_populates="run",
        cascade_delete=True,
        sa_relationship_kwargs={
            "order_by": "PipelineArtifact.created_at",
        },
    )
    events: list["PipelineRunEvent"] = Relationship(
        back_populates="run",
        cascade_delete=True,
        sa_relationship_kwargs={
            "order_by": "PipelineRunEvent.created_at",
        },
    )

    __table_args__ = (
        Index(
            "ix_pipeline_runs_queue",
            "status",
            "created_at",
        ),
    )


class PipelineArtifact(SQLModel, table=True):
    __tablename__ = "pipeline_artifacts"

    pipeline_artifacts_id: str = Field(
        default_factory=uuid_string,
        sa_column=Column(
            String(36),
            primary_key=True,
            default=uuid_string,
            nullable=False,
        ),
    )
    pipeline_runs_id: str = Field(
        sa_column=Column(
            String(36),
            ForeignKey(
                "pipeline_runs.pipeline_runs_id",
                ondelete="CASCADE",
            ),
            index=True,
            nullable=False,
        ),
    )
    artifact_type: str = Field(
        sa_column=Column(
            String(64),
            index=True,
            nullable=False,
        ),
    )
    object_key: str = Field(
        sa_column=Column(
            String(1024),
            unique=True,
            nullable=False,
        ),
    )
    content_type: str = Field(
        default="application/octet-stream",
        sa_column=Column(
            String(255),
            default="application/octet-stream",
            nullable=False,
        ),
    )
    size_bytes: int = Field(
        default=0,
        sa_column=Column(
            BigInteger,
            default=0,
            nullable=False,
        ),
    )
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
        ),
    )

    run: PipelineRun | None = Relationship(
        back_populates="artifacts",
    )

    __table_args__ = (
        UniqueConstraint(
            "pipeline_runs_id",
            "artifact_type",
            "object_key",
            name="uq_pipeline_artifact_run_type_key",
        ),
    )


class PipelineRunEvent(SQLModel, table=True):
    __tablename__ = "pipeline_run_events"

    pipeline_run_events_id: str = Field(
        default_factory=uuid_string,
        sa_column=Column(
            String(36),
            primary_key=True,
            default=uuid_string,
            nullable=False,
        ),
    )
    pipeline_runs_id: str = Field(
        sa_column=Column(
            String(36),
            ForeignKey(
                "pipeline_runs.pipeline_runs_id",
                ondelete="CASCADE",
            ),
            index=True,
            nullable=False,
        ),
    )
    stage: str = Field(
        sa_column=Column(String(64), nullable=False),
    )
    progress: int = Field(
        ge=0,
        le=100,
        sa_column=Column(Integer, nullable=False),
    )
    message: str | None = Field(
        default=None,
        sa_column=Column(String(1024), nullable=True),
    )
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
            index=True,
        ),
    )

    run: PipelineRun | None = Relationship(back_populates="events")
