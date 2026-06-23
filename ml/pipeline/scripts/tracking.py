"""Simple tracking helpers."""

from __future__ import annotations

from .config import PipelineConfig
from .schemas import DetectionRecord


def assign_track_ids(detections: list[DetectionRecord], config: PipelineConfig) -> None:
    active: dict[int, DetectionRecord] = {}
    next_track_id = 1

    detections_by_frame: dict[int, list[DetectionRecord]] = {}
    for detection in detections:
        detections_by_frame.setdefault(detection.frame_index, []).append(detection)

    for frame_index in sorted(detections_by_frame):
        used_tracks: set[int] = set()
        for detection in detections_by_frame[frame_index]:
            best_track_id: int | None = None
            best_iou = 0.0

            for track_id, last_detection in active.items():
                if track_id in used_tracks:
                    continue
                frame_gap = frame_index - last_detection.frame_index
                if frame_gap < 0:
                    continue
                max_gap = config.frame_stride * max(1, config.tracking.max_gap_frames)
                if frame_gap > max_gap:
                    continue
                value = bbox_iou(detection.bbox_xyxy, last_detection.bbox_xyxy)
                if value > best_iou:
                    best_iou = value
                    best_track_id = track_id

            if best_track_id is not None and best_iou >= config.tracking.iou_min:
                detection.track_id = best_track_id
                active[best_track_id] = detection
                used_tracks.add(best_track_id)
            else:
                detection.track_id = next_track_id
                active[next_track_id] = detection
                used_tracks.add(next_track_id)
                next_track_id += 1


def bbox_iou(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    ax1, ay1, ax2, ay2 = first
    bx1, by1, bx2, by2 = second

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    intersection = iw * ih
    if intersection <= 0:
        return 0.0

    first_area = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    second_area = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = first_area + second_area - intersection
    return intersection / union if union > 0 else 0.0
