#!/usr/bin/env python3
"""Extract detector-hit frames from video for CVAT hard-negative review."""

from __future__ import annotations

import argparse
import csv
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from xml.dom import minidom
from xml.etree import ElementTree as ET

import cv2

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "matplotlib"))

from ultralytics import YOLO


@dataclass
class BoxRecord:
    label: str
    conf: float
    xtl: float
    ytl: float
    xbr: float
    ybr: float


@dataclass
class ImageRecord:
    image_id: int
    name: str
    source_frame_index: int
    timestamp_sec: float
    width: int
    height: int
    boxes: list[BoxRecord]


@dataclass
class BBoxMemory:
    label: str
    xtl: float
    ytl: float
    xbr: float
    ybr: float
    last_seen_timestamp_sec: float
    last_saved_timestamp_sec: float

    @property
    def xyxy(self) -> tuple[float, float, float, float]:
        return self.xtl, self.ytl, self.xbr, self.ybr

    def update_seen(self, box: BoxRecord, timestamp_sec: float) -> None:
        self.xtl = box.xtl
        self.ytl = box.ytl
        self.xbr = box.xbr
        self.ybr = box.ybr
        self.last_seen_timestamp_sec = timestamp_sec


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract video frames with YOLO detections and create CVAT annotations.xml."
    )
    parser.add_argument("--input", required=True, type=Path, help="Input video path.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory. Defaults to outputs/hard_negatives/<run_id>.",
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=Path("models/detection/best.pt"),
        help="YOLO detector model path.",
    )
    parser.add_argument(
        "--conf", type=float, default=0.50, help="Minimum detector confidence."
    )
    parser.add_argument(
        "--iou", type=float, default=0.50, help="YOLO NMS IoU threshold."
    )
    parser.add_argument(
        "--same-bbox-iou",
        type=float,
        default=0.50,
        help="IoU threshold used to treat detections as the same bbox over time.",
    )
    parser.add_argument(
        "--same-bbox-min-interval-sec",
        type=float,
        default=5.0,
        help="Save the same bbox no more often than this interval.",
    )
    parser.add_argument(
        "--imgsz", type=int, default=960, help="YOLO inference image size."
    )
    parser.add_argument(
        "--device", default=None, help="Torch/Ultralytics device, e.g. cpu or 0."
    )
    parser.add_argument(
        "--frame-stride",
        type=int,
        default=1,
        help="Process every Nth frame. Use 1 to scan every frame.",
    )
    parser.add_argument(
        "--start-sec", type=float, default=0.0, help="Start time in seconds."
    )
    parser.add_argument(
        "--end-sec", type=float, default=None, help="Optional end time in seconds."
    )
    parser.add_argument(
        "--jpeg-quality",
        type=int,
        default=95,
        help="Saved frame JPEG quality, 1-100.",
    )
    parser.add_argument(
        "--max-images",
        type=int,
        default=None,
        help="Stop after saving this many hit frames.",
    )
    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="Do not save bbox overlay images to preview/.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[3]
    input_path = resolve_path(project_root, args.input)
    model_path = resolve_path(project_root, args.model)
    output_dir = (
        resolve_path(project_root, args.output_dir)
        if args.output_dir
        else default_output_dir(project_root, input_path)
    )

    if args.frame_stride < 1:
        raise ValueError("--frame-stride must be >= 1")
    if args.same_bbox_min_interval_sec < 0:
        raise ValueError("--same-bbox-min-interval-sec must be >= 0")
    if not input_path.exists():
        raise FileNotFoundError(input_path)
    if not model_path.exists():
        raise FileNotFoundError(model_path)

    images_dir = output_dir / "images"
    preview_dir = None if args.no_preview else output_dir / "preview"
    images_dir.mkdir(parents=True, exist_ok=True)
    if preview_dir is not None:
        preview_dir.mkdir(parents=True, exist_ok=True)

    model = YOLO(str(model_path))
    label_names = normalize_label_names(getattr(model, "names", {}) or {})
    image_records = extract_frames(
        args, input_path, images_dir, preview_dir, model, label_names
    )
    write_cvat_xml(
        output_dir / "annotations.xml", image_records, label_names, input_path
    )
    write_detections_csv(output_dir / "detections.csv", image_records)

    print(f"input: {input_path}")
    print(f"output: {output_dir}")
    print(f"model: {model_path}")
    print(f"saved hit frames: {len(image_records)}")
    if preview_dir is not None:
        print(f"preview: {preview_dir}")
    print(f"annotations: {output_dir / 'annotations.xml'}")
    return 0


def resolve_path(project_root: Path, value: Path | None) -> Path:
    if value is None:
        raise ValueError("Path value is required")
    return value if value.is_absolute() else project_root / value


def default_output_dir(project_root: Path, input_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return (
        project_root
        / "outputs"
        / "hard_negatives"
        / f"{timestamp}_{safe_stem(input_path.stem)}"
    )


def safe_stem(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", value).strip("_") or "video"


def normalize_label_names(names: dict | list) -> dict[int, str]:
    if isinstance(names, list):
        return {index: str(name) for index, name in enumerate(names)}
    return {int(index): str(name) for index, name in names.items()}


def extract_frames(
    args: argparse.Namespace,
    input_path: Path,
    images_dir: Path,
    preview_dir: Path | None,
    model: YOLO,
    label_names: dict[int, str],
) -> list[ImageRecord]:
    cap = cv2.VideoCapture(str(input_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {input_path}")

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0) or 25.0
    if args.start_sec > 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(args.start_sec * fps))

    records: list[ImageRecord] = []
    bbox_memories: list[BBoxMemory] = []
    frame_index = int(cap.get(cv2.CAP_PROP_POS_FRAMES) or 0)
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            timestamp_sec = frame_index / fps
            if args.end_sec is not None and timestamp_sec > args.end_sec:
                break

            should_process = frame_index % args.frame_stride == 0
            if should_process:
                boxes = detect_boxes(model, frame, label_names, args)
                boxes_to_save = filter_boxes_for_saving(
                    boxes, bbox_memories, timestamp_sec, args
                )
                if boxes_to_save:
                    image_name = f"frame_{frame_index:06d}_t{timestamp_sec:09.3f}.jpg"
                    image_path = images_dir / image_name
                    cv2.imwrite(
                        str(image_path),
                        frame,
                        [int(cv2.IMWRITE_JPEG_QUALITY), int(args.jpeg_quality)],
                    )
                    if preview_dir is not None:
                        preview_path = preview_dir / image_name
                        preview = draw_preview(frame, boxes_to_save)
                        cv2.imwrite(
                            str(preview_path),
                            preview,
                            [int(cv2.IMWRITE_JPEG_QUALITY), int(args.jpeg_quality)],
                        )
                    records.append(
                        ImageRecord(
                            image_id=len(records),
                            name=f"images/{image_name}",
                            source_frame_index=frame_index,
                            timestamp_sec=timestamp_sec,
                            width=int(frame.shape[1]),
                            height=int(frame.shape[0]),
                            boxes=boxes_to_save,
                        )
                    )
                    if args.max_images is not None and len(records) >= args.max_images:
                        break

            frame_index += 1
    finally:
        cap.release()
    return records


def draw_preview(frame, boxes: list[BoxRecord]):
    preview = frame.copy()
    for box in boxes:
        draw_box(preview, box)
    return preview


def draw_box(image, box: BoxRecord) -> None:
    color = (0, 210, 255)
    x1, y1, x2, y2 = [
        int(round(value)) for value in (box.xtl, box.ytl, box.xbr, box.ybr)
    ]
    cv2.rectangle(image, (x1, y1), (x2, y2), color, 3)

    label = f"{box.label} {box.conf:.2f}"
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.8
    thickness = 2
    (text_width, text_height), baseline = cv2.getTextSize(
        label, font, font_scale, thickness
    )
    text_x = max(0, min(x1, image.shape[1] - text_width - 4))
    text_y = max(text_height + baseline + 4, y1 - 6)
    background_top_left = (text_x, text_y - text_height - baseline - 4)
    background_bottom_right = (text_x + text_width + 4, text_y + baseline)
    cv2.rectangle(image, background_top_left, background_bottom_right, color, -1)
    cv2.putText(
        image,
        label,
        (text_x + 2, text_y - 3),
        font,
        font_scale,
        (0, 0, 0),
        thickness,
        cv2.LINE_AA,
    )


def filter_boxes_for_saving(
    boxes: list[BoxRecord],
    bbox_memories: list[BBoxMemory],
    timestamp_sec: float,
    args: argparse.Namespace,
) -> list[BoxRecord]:
    prune_old_bbox_memories(
        bbox_memories, timestamp_sec, max(30.0, args.same_bbox_min_interval_sec * 3)
    )

    boxes_to_save: list[BoxRecord] = []
    matched_memory_indices: set[int] = set()
    for box in boxes:
        match_index = find_matching_bbox_memory(
            box, bbox_memories, args.same_bbox_iou, matched_memory_indices
        )
        if match_index is None:
            bbox_memories.append(
                BBoxMemory(
                    label=box.label,
                    xtl=box.xtl,
                    ytl=box.ytl,
                    xbr=box.xbr,
                    ybr=box.ybr,
                    last_seen_timestamp_sec=timestamp_sec,
                    last_saved_timestamp_sec=timestamp_sec,
                )
            )
            boxes_to_save.append(box)
            continue

        matched_memory_indices.add(match_index)
        memory = bbox_memories[match_index]
        should_save = (
            timestamp_sec - memory.last_saved_timestamp_sec
            >= args.same_bbox_min_interval_sec
        )
        memory.update_seen(box, timestamp_sec)
        if should_save:
            memory.last_saved_timestamp_sec = timestamp_sec
            boxes_to_save.append(box)

    return boxes_to_save


def prune_old_bbox_memories(
    bbox_memories: list[BBoxMemory],
    timestamp_sec: float,
    max_age_sec: float,
) -> None:
    bbox_memories[:] = [
        memory
        for memory in bbox_memories
        if timestamp_sec - memory.last_seen_timestamp_sec <= max_age_sec
    ]


def find_matching_bbox_memory(
    box: BoxRecord,
    bbox_memories: list[BBoxMemory],
    min_iou: float,
    excluded_indices: set[int],
) -> int | None:
    best_index: int | None = None
    best_iou = 0.0
    box_xyxy = (box.xtl, box.ytl, box.xbr, box.ybr)
    for index, memory in enumerate(bbox_memories):
        if index in excluded_indices or memory.label != box.label:
            continue
        current_iou = bbox_iou(box_xyxy, memory.xyxy)
        if current_iou > best_iou:
            best_iou = current_iou
            best_index = index
    if best_index is not None and best_iou >= min_iou:
        return best_index
    return None


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


def detect_boxes(
    model: YOLO,
    frame,
    label_names: dict[int, str],
    args: argparse.Namespace,
) -> list[BoxRecord]:
    predict_kwargs = {
        "conf": args.conf,
        "iou": args.iou,
        "imgsz": args.imgsz,
        "verbose": False,
    }
    if args.device is not None:
        predict_kwargs["device"] = args.device

    boxes: list[BoxRecord] = []
    frame_height, frame_width = frame.shape[:2]
    for result in model.predict(frame, **predict_kwargs):
        if result.boxes is None:
            continue
        for box in result.boxes:
            conf = float(box.conf[0].detach().cpu())
            if conf < args.conf:
                continue
            class_id = int(box.cls[0].detach().cpu())
            x1, y1, x2, y2 = [
                float(value) for value in box.xyxy[0].detach().cpu().tolist()
            ]
            xtl = min(float(frame_width - 1), max(0.0, x1))
            ytl = min(float(frame_height - 1), max(0.0, y1))
            xbr = min(float(frame_width - 1), max(0.0, x2))
            ybr = min(float(frame_height - 1), max(0.0, y2))
            if xbr <= xtl or ybr <= ytl:
                continue
            boxes.append(
                BoxRecord(
                    label=label_names.get(class_id, str(class_id)),
                    conf=conf,
                    xtl=xtl,
                    ytl=ytl,
                    xbr=xbr,
                    ybr=ybr,
                )
            )
    return boxes


def write_cvat_xml(
    path: Path,
    image_records: list[ImageRecord],
    label_names: dict[int, str],
    input_path: Path,
) -> None:
    annotations = ET.Element("annotations")
    ET.SubElement(annotations, "version").text = "1.1"

    meta = ET.SubElement(annotations, "meta")
    task = ET.SubElement(meta, "task")
    ET.SubElement(task, "id").text = "0"
    ET.SubElement(task, "name").text = f"hard_negatives_{input_path.stem}"
    ET.SubElement(task, "size").text = str(len(image_records))
    ET.SubElement(task, "mode").text = "annotation"
    ET.SubElement(task, "overlap").text = "0"
    ET.SubElement(task, "bugtracker")
    now = datetime.now().isoformat(timespec="seconds")
    ET.SubElement(task, "created").text = now
    ET.SubElement(task, "updated").text = now
    ET.SubElement(task, "subset").text = "default"
    ET.SubElement(task, "start_frame").text = "0"
    ET.SubElement(task, "stop_frame").text = str(max(0, len(image_records) - 1))
    ET.SubElement(task, "frame_filter")

    segments = ET.SubElement(task, "segments")
    segment = ET.SubElement(segments, "segment")
    ET.SubElement(segment, "id").text = "0"
    ET.SubElement(segment, "start").text = "0"
    ET.SubElement(segment, "stop").text = str(max(0, len(image_records) - 1))
    ET.SubElement(segment, "url")

    owner = ET.SubElement(task, "owner")
    ET.SubElement(owner, "username").text = "auto"
    ET.SubElement(owner, "email")
    ET.SubElement(task, "assignee")

    labels = ET.SubElement(task, "labels")
    for name in sorted(set(label_names.values())):
        label = ET.SubElement(labels, "label")
        ET.SubElement(label, "name").text = name
        ET.SubElement(label, "color").text = "#1f77b4"
        ET.SubElement(label, "type").text = "any"
        attributes = ET.SubElement(label, "attributes")
        for attribute_name in ("model_conf", "source_frame_index", "timestamp_sec"):
            attribute = ET.SubElement(attributes, "attribute")
            ET.SubElement(attribute, "name").text = attribute_name
            ET.SubElement(attribute, "mutable").text = "False"
            ET.SubElement(attribute, "input_type").text = "text"
            ET.SubElement(attribute, "default_value")
            ET.SubElement(attribute, "values")

    ET.SubElement(meta, "dumped").text = now

    for record in image_records:
        image = ET.SubElement(
            annotations,
            "image",
            {
                "id": str(record.image_id),
                "name": record.name,
                "width": str(record.width),
                "height": str(record.height),
            },
        )
        for box in record.boxes:
            box_node = ET.SubElement(
                image,
                "box",
                {
                    "label": box.label,
                    "source": "auto",
                    "occluded": "0",
                    "xtl": f"{box.xtl:.2f}",
                    "ytl": f"{box.ytl:.2f}",
                    "xbr": f"{box.xbr:.2f}",
                    "ybr": f"{box.ybr:.2f}",
                    "z_order": "0",
                },
            )
            add_attribute(box_node, "model_conf", f"{box.conf:.4f}")
            add_attribute(
                box_node, "source_frame_index", str(record.source_frame_index)
            )
            add_attribute(box_node, "timestamp_sec", f"{record.timestamp_sec:.3f}")

    path.parent.mkdir(parents=True, exist_ok=True)
    rough = ET.tostring(annotations, encoding="utf-8")
    pretty = minidom.parseString(rough).toprettyxml(indent="  ", encoding="utf-8")
    path.write_bytes(pretty)


def add_attribute(parent: ET.Element, name: str, value: str) -> None:
    attribute = ET.SubElement(parent, "attribute", {"name": name})
    attribute.text = value


def write_detections_csv(path: Path, image_records: list[ImageRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "image_name",
        "source_frame_index",
        "timestamp_sec",
        "label",
        "conf",
        "xtl",
        "ytl",
        "xbr",
        "ybr",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in image_records:
            for box in record.boxes:
                writer.writerow(
                    {
                        "image_name": record.name,
                        "source_frame_index": record.source_frame_index,
                        "timestamp_sec": f"{record.timestamp_sec:.3f}",
                        "label": box.label,
                        "conf": f"{box.conf:.4f}",
                        "xtl": f"{box.xtl:.2f}",
                        "ytl": f"{box.ytl:.2f}",
                        "xbr": f"{box.xbr:.2f}",
                        "ybr": f"{box.ybr:.2f}",
                    }
                )


if __name__ == "__main__":
    raise SystemExit(main())
