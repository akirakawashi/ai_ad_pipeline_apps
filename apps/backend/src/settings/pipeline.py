from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class PipelineSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PIPELINE_",
        extra="ignore",
        frozen=True,
    )

    detector_model_path: Path = Field(
        default=Path("models/detection/best.pt"),
    )
    classifier_model_path: Path = Field(
        default=Path("models/classification/best.pt"),
    )
    brand_overrides_path: Path | None = Field(
        default=Path("ml/pipeline/brand_overrides.csv"),
    )
    frame_stride: int = Field(default=1, ge=1)
    device: str | None = "0"
    worker_poll_interval_sec: float = Field(default=2.0, gt=0)
    worker_temp_dir: Path = Field(
        default=Path(".runtime/worker"),
    )
