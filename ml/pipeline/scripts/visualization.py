"""Annotated media helpers."""

from __future__ import annotations

from dataclasses import replace
from math import ceil
from pathlib import Path

import cv2

from .config import PipelineConfig
from .schemas import DetectionRecord, FrameRecord, InputMetadata, TrackRecord


COLORS = {
    "mts": (0, 0, 255),
    "plus7": (255, 180, 0),
    "miranda": (30, 180, 60),
    "other": (0, 255, 255),
}


def write_annotated_media(
    output_dir: Path,
    frames: list[FrameRecord] | None,
    detections: list[DetectionRecord],
    tracks: list[TrackRecord],
    metadata: InputMetadata,
    config: PipelineConfig,
) -> None:
    annotated_dir = None
    if config.rendering.save_annotated_frames:
        annotated_dir = output_dir / "frames" / "annotated"
        annotated_dir.mkdir(parents=True, exist_ok=True)

    tracks_by_id = {track.track_id: track for track in tracks}
    detections_by_frame = build_render_detections_by_frame(detections, metadata, config)

    if metadata.input_type == "video" and frames is None:
        write_annotated_video_from_source(
            output_dir,
            detections_by_frame,
            tracks_by_id,
            metadata,
            config,
            annotated_dir,
        )
        return

    if frames is None:
        return

    writer = create_annotated_video_writer(
        output_dir / "video" / "annotated_video.mp4", frames, metadata
    )
    try:
        for frame in frames:
            annotated = frame.image.copy()
            for detection in detections_by_frame.get(frame.frame_index, []):
                track = tracks_by_id.get(detection.track_id or -1)
                draw_detection(annotated, detection, track)

            if annotated_dir is not None:
                frame_path = annotated_dir / f"frame_{frame.frame_index:06d}.jpg"
                cv2.imwrite(str(frame_path), annotated)
            if writer is not None:
                writer.write(annotated)
    finally:
        if writer is not None:
            writer.release()


def write_annotated_video_from_source(
    output_dir: Path,
    detections_by_frame: dict[int, list[DetectionRecord]],
    tracks_by_id: dict[int, TrackRecord],
    metadata: InputMetadata,
    config: PipelineConfig,
    annotated_dir: Path | None,
) -> None:
    cap = cv2.VideoCapture(str(metadata.source_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {metadata.source_path}")

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0) or metadata.fps or 25.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or metadata.width)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or metadata.height)

    output_video = output_dir / "video" / "annotated_video.mp4"
    output_video.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(output_video),
        video_writer_fourcc("mp4v"),
        fps,
        (width, height),
    )
    if not writer.isOpened():
        cap.release()
        raise RuntimeError(f"Could not create annotated video: {output_video}")

    frame_index = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            annotated = frame.copy()
            frame_detections = detections_by_frame.get(frame_index, [])
            for detection in frame_detections:
                track = tracks_by_id.get(detection.track_id or -1)
                draw_detection(annotated, detection, track)

            if annotated_dir is not None and frame_detections:
                frame_path = annotated_dir / f"frame_{frame_index:06d}.jpg"
                cv2.imwrite(str(frame_path), annotated)

            writer.write(annotated)
            frame_index += 1
    finally:
        cap.release()
        writer.release()


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


def draw_detection(
    image,
    detection: DetectionRecord,
    track: TrackRecord | None,
) -> None:
    brand = display_brand(detection, track)
    color = COLORS.get(brand, COLORS["other"])
    x1, y1, x2, y2 = (int(round(value)) for value in detection.bbox_xyxy)
    cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)

    label = brand.upper()
    text_y = max(18, y1 - 6)
    cv2.putText(
        image,
        label,
        (x1, text_y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        color,
        2,
        cv2.LINE_AA,
    )


def display_brand(detection: DetectionRecord, track: TrackRecord | None) -> str:
    if track:
        return track.business_brand or "other"
    return detection.business_brand or "other"


def create_annotated_video_writer(
    path: Path,
    frames: list[FrameRecord],
    metadata: InputMetadata,
):
    if metadata.input_type != "video" or not frames:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    fps = max(1.0, metadata.fps / max(1, metadata.frame_stride))
    first = frames[0]
    writer = cv2.VideoWriter(
        str(path),
        video_writer_fourcc("mp4v"),
        fps,
        (first.width, first.height),
    )
    if not writer.isOpened():
        raise RuntimeError(f"Could not create annotated video: {path}")
    return writer


def video_writer_fourcc(codec: str) -> int:
    return int(getattr(cv2, "VideoWriter_fourcc")(*codec))
