from __future__ import annotations

from application.common.dto.base import ApplicationDTO


class ProcessingArtifactInputDTO(ApplicationDTO):
    """Артефакт, уже загруженный worker-ом в объектное хранилище."""

    relative_path: str
    content_type: str
    size_bytes: int


class ProcessingVideoMetadataDTO(ApplicationDTO):
    fps: float
    frame_count: int
    frame_stride: int
    width: int
    height: int
