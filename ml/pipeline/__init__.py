"""Outdoor advertising analysis pipeline."""

import os
import tempfile
from pathlib import Path

os.environ.setdefault(
    "MPLCONFIGDIR",
    str(Path(tempfile.gettempdir()) / "matplotlib"),
)

from .scripts.config import PipelineConfig
from .scripts.runner import (
    PipelineModels,
    PipelineRunResult,
    load_pipeline_models,
    run_pipeline,
)

__all__ = [
    "PipelineConfig",
    "PipelineModels",
    "PipelineRunResult",
    "load_pipeline_models",
    "run_pipeline",
]
