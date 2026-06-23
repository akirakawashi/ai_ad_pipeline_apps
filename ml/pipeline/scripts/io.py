"""Input frame loading helpers."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import cv2

from .schemas import FrameRecord, InputMetadata


IMAGE_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
VIDEO_EXTENSIONS = {".avi", ".m4v", ".mkv", ".mov", ".mp4", ".webm"}


def detect_input_type(input_path: Path) -> str:
    suffix = input_path.suffix.casefold()
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    raise ValueError(f"Unsupported input extension: {input_path.suffix}")


def load_frames(
    input_path: Path, frame_stride: int
) -> tuple[InputMetadata, list[FrameRecord]]:
    metadata = load_metadata(input_path, frame_stride)
    frames = list(iter_frames(input_path, frame_stride))
    if not frames:
        raise RuntimeError(f"No frames were read from input: {input_path}")
    return metadata, frames


def load_metadata(input_path: Path, frame_stride: int) -> InputMetadata:
    if frame_stride < 1:
        raise ValueError("frame_stride must be >= 1")
    if not input_path.exists():
        raise FileNotFoundError(input_path)

    input_type = detect_input_type(input_path)
    if input_type == "image":
        metadata, _ = _load_image(input_path, frame_stride)
        return metadata
    return _load_video_metadata(input_path, frame_stride)


def iter_frames(input_path: Path, frame_stride: int) -> Iterator[FrameRecord]:
    if frame_stride < 1:
        raise ValueError("frame_stride must be >= 1")
    if not input_path.exists():
        raise FileNotFoundError(input_path)

    input_type = detect_input_type(input_path)
    if input_type == "image":
        _, frames = _load_image(input_path, frame_stride)
        yield from frames
        return
    yield from _iter_video_frames(input_path, frame_stride)


def _load_image(
    input_path: Path, frame_stride: int
) -> tuple[InputMetadata, list[FrameRecord]]:
    image = cv2.imread(str(input_path), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"Could not read image: {input_path}")

    height, width = image.shape[:2]
    metadata = InputMetadata(
        source_path=input_path,
        input_type="image",
        fps=1.0,
        frame_count=1,
        frame_stride=frame_stride,
        delta_t_sec=1.0,
        width=width,
        height=height,
    )
    frame = FrameRecord(
        frame_index=0,
        timestamp_sec=0.0,
        width=width,
        height=height,
        delta_t_sec=1.0,
        image=image,
    )
    return metadata, [frame]


def _load_video_metadata(input_path: Path, frame_stride: int) -> InputMetadata:
    cap = cv2.VideoCapture(str(input_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {input_path}")

    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        if fps <= 0:
            fps = 25.0
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    finally:
        cap.release()

    return InputMetadata(
        source_path=input_path,
        input_type="video",
        fps=fps,
        frame_count=frame_count,
        frame_stride=frame_stride,
        delta_t_sec=frame_stride / fps,
        width=width,
        height=height,
    )


def _iter_video_frames(input_path: Path, frame_stride: int) -> Iterator[FrameRecord]:
    cap = cv2.VideoCapture(str(input_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {input_path}")

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    if fps <= 0:
        fps = 25.0
    delta_t_sec = frame_stride / fps
    frame_index = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if frame_index % frame_stride == 0:
                yield FrameRecord(
                    frame_index=frame_index,
                    timestamp_sec=frame_index / fps,
                    width=frame.shape[1],
                    height=frame.shape[0],
                    delta_t_sec=delta_t_sec,
                    image=frame,
                )
            frame_index += 1
    finally:
        cap.release()
