"""Какие рамки видны в каком кадре — данные для оверлея плеера.

Рисованием здесь ничего не занимается и не должно. Раньше этот файл ещё и
собирал копию видео с вписанными рамками; её убрали — плеер на фронте рисует
их сам поверх исходника по `overlay.json`, а копия весила столько же, сколько
оригинал, и не открывалась никем.

Отсюда идёт ровно одна дорога: `viewer/payload.py` берёт результат
`build_render_detections_by_frame` и складывает из него `overlay.json`.
"""

from __future__ import annotations

from dataclasses import replace
from math import ceil

from .config import PipelineConfig
from .schemas import DetectionRecord, InputMetadata


def build_render_detections_by_frame(
    detections: list[DetectionRecord],
    metadata: InputMetadata,
    config: PipelineConfig,
) -> dict[int, list[DetectionRecord]]:
    visible_detections = [
        detection for detection in detections if detection.business_visible
    ]
    detections_by_frame: dict[int, list[DetectionRecord]] = {}
    detections_by_object: dict[int, list[DetectionRecord]] = {}

    for detection in visible_detections:
        detections_by_frame.setdefault(detection.frame_index, []).append(detection)
        if detection.object_id is not None:
            detections_by_object.setdefault(detection.object_id, []).append(detection)

    max_gap_frames = render_gap_fill_max_frames(metadata, config)
    if max_gap_frames <= 0:
        return detections_by_frame

    for object_detections in detections_by_object.values():
        ordered = sorted(
            object_detections, key=lambda item: (item.frame_index, item.det_index)
        )
        for previous, current in zip(ordered, ordered[1:]):
            frame_gap = current.frame_index - previous.frame_index
            missing_frames = frame_gap - 1
            if missing_frames <= 0 or missing_frames > max_gap_frames:
                continue
            for offset in range(1, frame_gap):
                frame_index = previous.frame_index + offset
                ratio = offset / frame_gap
                interpolated = interpolate_detection(
                    previous, current, frame_index, ratio, metadata
                )
                detections_by_frame.setdefault(frame_index, []).append(interpolated)

    for frame_detections in detections_by_frame.values():
        frame_detections.sort(key=lambda item: (item.object_id or 0, item.det_index))

    return detections_by_frame


def render_gap_fill_max_frames(metadata: InputMetadata, config: PipelineConfig) -> int:
    if config.rendering.gap_fill_max_sec <= 0:
        return 0
    fps = metadata.fps
    if fps <= 0 and metadata.delta_t_sec > 0:
        fps = 1.0 / metadata.delta_t_sec
    if fps <= 0:
        return 0
    return max(0, int(ceil(fps * config.rendering.gap_fill_max_sec)))


def interpolate_detection(
    previous: DetectionRecord,
    current: DetectionRecord,
    frame_index: int,
    ratio: float,
    metadata: InputMetadata,
) -> DetectionRecord:
    x1 = lerp(previous.bbox_x1, current.bbox_x1, ratio)
    y1 = lerp(previous.bbox_y1, current.bbox_y1, ratio)
    x2 = lerp(previous.bbox_x2, current.bbox_x2, ratio)
    y2 = lerp(previous.bbox_y2, current.bbox_y2, ratio)
    width = max(0.0, x2 - x1)
    height = max(0.0, y2 - y1)
    area = width * height
    frame_area = max(1.0, float(metadata.width * metadata.height))
    center_x = (x1 + x2) / 2.0
    center_y = (y1 + y2) / 2.0
    timestamp_sec = (
        frame_index / metadata.fps
        if metadata.fps > 0
        else lerp(
            previous.timestamp_sec,
            current.timestamp_sec,
            ratio,
        )
    )

    return replace(
        previous,
        frame_index=frame_index,
        timestamp_sec=timestamp_sec,
        det_conf=lerp(previous.det_conf, current.det_conf, ratio),
        bbox_x1=x1,
        bbox_y1=y1,
        bbox_x2=x2,
        bbox_y2=y2,
        bbox_width=width,
        bbox_height=height,
        bbox_aspect_ratio=width / height if height > 0 else 0.0,
        bbox_area=area,
        area_ratio=area / frame_area,
        center_x=center_x,
        center_y=center_y,
        center_x_norm=center_x / metadata.width if metadata.width > 0 else 0.0,
        center_y_norm=center_y / metadata.height if metadata.height > 0 else 0.0,
        crop_path="",
    )


def lerp(start: float, end: float, ratio: float) -> float:
    return start + (end - start) * ratio
