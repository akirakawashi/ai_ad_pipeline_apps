"""YOLO detection helpers."""

from __future__ import annotations

from typing import Any, cast

from ultralytics import YOLO

from .config import PipelineConfig
from .schemas import DetectionRecord, FrameRecord, InputMetadata
from .visibility import fill_geometry_fields


def load_detector(config: PipelineConfig) -> YOLO:
    if not config.detector_model_path.exists():
        raise FileNotFoundError(config.detector_model_path)
    return YOLO(str(config.detector_model_path))


def run_detection(
    model: YOLO,
    frames: list[FrameRecord],
    metadata: InputMetadata,
    config: PipelineConfig,
) -> list[DetectionRecord]:
    detections: list[DetectionRecord] = []
    names = getattr(model, "names", {}) or {}

    for frame in frames:
        predict_kwargs: dict[str, object] = {
            "conf": config.detection.confidence_min,
            "iou": config.detection.iou,
            "verbose": False,
        }
        if config.detection.image_size:
            predict_kwargs["imgsz"] = config.detection.image_size
        if config.device is not None:
            predict_kwargs["device"] = config.device

        results = cast(Any, model).predict(frame.image, **predict_kwargs)
        frame_det_index = 0
        for result in results:
            if result.boxes is None:
                continue
            for box in cast(Any, result.boxes):
                xyxy = box.xyxy[0].detach().cpu().tolist()
                conf = float(box.conf[0].detach().cpu())
                class_id = int(box.cls[0].detach().cpu())
                class_name = str(names.get(class_id, class_id))
                x1, y1, x2, y2 = (float(value) for value in xyxy)
                width = max(0.0, x2 - x1)
                height = max(0.0, y2 - y1)
                aspect_ratio = width / height if height > 0 else 0.0
                area = width * height
                area_ratio = area / max(1.0, frame.width * frame.height)

                if not _passes_detection_gate(
                    width, height, area_ratio, aspect_ratio, config
                ):
                    continue

                detection = DetectionRecord(
                    run_id=config.run_id,
                    source_path=str(metadata.source_path),
                    input_type=metadata.input_type,
                    frame_index=frame.frame_index,
                    timestamp_sec=frame.timestamp_sec,
                    sample_delta_t_sec=frame.delta_t_sec,
                    det_index=frame_det_index,
                    track_id=None,
                    det_class=class_name,
                    det_conf=conf,
                    bbox_x1=x1,
                    bbox_y1=y1,
                    bbox_x2=x2,
                    bbox_y2=y2,
                    bbox_width=width,
                    bbox_height=height,
                    bbox_aspect_ratio=aspect_ratio,
                    bbox_area=area,
                    area_ratio=area_ratio,
                    center_x=0.0,
                    center_y=0.0,
                    center_x_norm=0.0,
                    center_y_norm=0.0,
                    position_label="",
                    position_weight=0.0,
                )
                fill_geometry_fields(detection, frame, config)
                detections.append(detection)
                frame_det_index += 1

    return detections


def _passes_detection_gate(
    width: float,
    height: float,
    area_ratio: float,
    aspect_ratio: float,
    config: PipelineConfig,
) -> bool:
    return (
        width >= config.detection.min_width
        and height >= config.detection.min_height
        and area_ratio >= config.detection.min_area_ratio
        and config.detection.min_aspect_ratio
        <= aspect_ratio
        <= config.detection.max_aspect_ratio
    )
