from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.database.base import Base


def uuid_string() -> str:
    return str(uuid.uuid4())


class PipelineRunModel(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=uuid_string,
    )
    source_name: Mapped[str] = mapped_column(String(512))
    source_object_key: Mapped[str] = mapped_column(String(1024), unique=True)
    source_content_type: Mapped[str | None] = mapped_column(String(255))
    source_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)

    status: Mapped[str] = mapped_column(
        String(32),
        index=True,
        default="uploading",
    )
    stage: Mapped[str] = mapped_column(String(64), default="upload")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    status_message: Mapped[str | None] = mapped_column(String(1024))
    error_code: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(Text)

    fps: Mapped[float | None] = mapped_column(Float)
    frame_count: Mapped[int | None] = mapped_column(Integer)
    frame_stride: Mapped[int | None] = mapped_column(Integer)
    duration_sec: Mapped[float | None] = mapped_column(Float)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)

    worker_id: Mapped[str | None] = mapped_column(String(255), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    upload_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    artifacts: Mapped[list["PipelineArtifactModel"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="PipelineArtifactModel.created_at",
    )
    events: Mapped[list["PipelineRunEventModel"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="PipelineRunEventModel.created_at",
    )

    __table_args__ = (
        Index(
            "ix_pipeline_runs_queue",
            "status",
            "created_at",
        ),
    )


class PipelineArtifactModel(Base):
    __tablename__ = "pipeline_artifacts"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=uuid_string,
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="CASCADE"),
        index=True,
    )
    artifact_type: Mapped[str] = mapped_column(String(64), index=True)
    object_key: Mapped[str] = mapped_column(String(1024), unique=True)
    content_type: Mapped[str] = mapped_column(
        String(255),
        default="application/octet-stream",
    )
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    run: Mapped["PipelineRunModel"] = relationship(
        back_populates="artifacts"
    )

    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "artifact_type",
            "object_key",
            name="uq_pipeline_artifact_run_type_key",
        ),
    )


class PipelineRunEventModel(Base):
    __tablename__ = "pipeline_run_events"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=uuid_string,
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="CASCADE"),
        index=True,
    )
    stage: Mapped[str] = mapped_column(String(64))
    progress: Mapped[int] = mapped_column(Integer)
    message: Mapped[str | None] = mapped_column(String(1024))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )

    run: Mapped["PipelineRunModel"] = relationship(back_populates="events")
