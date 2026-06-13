#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
import random
import re
import shutil
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile
from xml.etree import ElementTree as ET


PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(PROJECT_ROOT / ".cache/matplotlib"))

import cv2
import torch
from ultralytics import YOLO


DEFAULT_MODEL_PATH = PROJECT_ROOT / "models/trained/yolo11x_finetune_hard_negatives_v1/best.pt"
DEFAULT_VIDEO_PATHS = [
    PROJECT_ROOT / "test.mp4",
    PROJECT_ROOT / "test_2.mp4",
    PROJECT_ROOT / "test_3.mp4",
    PROJECT_ROOT / "test_4.mp4",
]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "cvat_import/video_finetune_fp_review_all4"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect fine-tuned YOLO detections from videos and export event-based CVAT review files."
    )
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--videos", type=Path, nargs="+", default=DEFAULT_VIDEO_PATHS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--label-name", default="ad_object")
    parser.add_argument("--predict-conf", type=float, default=0.25)
    parser.add_argument("--export-conf", type=float, default=0.55)
    parser.add_argument("--iou", type=float, default=0.70)
    parser.add_argument("--imgsz", type=int, default=1280)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--vid-stride", type=int, default=10)
    parser.add_argument("--event-gap", type=int, default=90)
    parser.add_argument("--frames-per-event", type=int, default=3)
    parser.add_argument("--max-frames-per-video", type=int, default=80)
    parser.add_argument("--frame-prefix", default="video_hard")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--jpeg-quality", type=int, default=95)
    parser.add_argument("--no-shuffle", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def resolve_device(device: str) -> str:
    if device != "auto":
        if device != "cpu" and not torch.cuda.is_available():
            print(f"CUDA is not available, falling back from device={device!r} to device='cpu'.")
            return "cpu"
        return device
    return "0" if torch.cuda.is_available() else "cpu"


def append_text(parent: ET.Element, tag: str, text: object) -> ET.Element:
    child = ET.SubElement(parent, tag)
    child.text = str(text)
    return child


def safe_stem(path: Path) -> str:
    stem = re.sub(r"[^0-9A-Za-z_-]+", "_", path.stem).strip("_")
    return stem or "video"


def class_label(class_names: object, class_id: int) -> str:
    if isinstance(class_names, dict):
        return str(class_names.get(class_id, class_id))
    if isinstance(class_names, (list, tuple)) and 0 <= class_id < len(class_names):
        return str(class_names[class_id])
    return str(class_id)


def pick_evenly(values: list[int], count: int) -> list[int]:
    if count >= len(values):
        return values
    if count <= 1:
        return [values[len(values) // 2]]
    step = (len(values) - 1) / (count - 1)
    indexes = sorted({round(index * step) for index in range(count)})
    return [values[index] for index in indexes]


def group_frames(frames: list[int], event_gap: int) -> list[list[int]]:
    segments: list[list[int]] = []
    current_segment: list[int] = []
    for frame_index in frames:
        if not current_segment or frame_index - current_segment[-1] <= event_gap:
            current_segment.append(frame_index)
        else:
            segments.append(current_segment)
            current_segment = [frame_index]
    if current_segment:
        segments.append(current_segment)
    return segments


def video_metadata(video_path: Path) -> dict[str, int | float]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return {"fps": fps, "frame_count": frame_count, "width": width, "height": height}


def prepare_output(output_dir: Path, overwrite: bool) -> Path:
    if output_dir.exists():
        if not overwrite:
            raise FileExistsError(f"{output_dir} already exists. Re-run with --overwrite to rebuild it.")
        shutil.rmtree(output_dir)
    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    return images_dir


def collect_detections(
    model: YOLO,
    video_path: Path,
    args: argparse.Namespace,
) -> tuple[list[dict[str, object]], dict[str, int | float]]:
    meta = video_metadata(video_path)
    fps = float(meta["fps"])
    frame_count = int(meta["frame_count"])
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    rows: list[dict[str, object]] = []
    frame_index = 0
    processed_frames = 0
    names = model.names
    print(
        f"Scanning {video_path.name}: frames={frame_count}, fps={fps:.2f}, "
        f"stride={args.vid_stride}"
    )

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        if frame_index % args.vid_stride != 0:
            frame_index += 1
            continue

        result = model.predict(
            source=frame,
            imgsz=args.imgsz,
            conf=args.predict_conf,
            iou=args.iou,
            device=args.device,
            verbose=False,
        )[0]

        if result.boxes is not None:
            for box_index, box in enumerate(result.boxes):
                confidence = float(box.conf[0])
                class_id = int(box.cls[0])
                x1, y1, x2, y2 = [float(value) for value in box.xyxy[0].tolist()]
                rows.append(
                    {
                        "source_video": video_path.name,
                        "video_stem": safe_stem(video_path),
                        "frame": frame_index,
                        "time_sec": frame_index / fps,
                        "box_index": box_index,
                        "class_id": class_id,
                        "class_name": class_label(names, class_id),
                        "confidence": confidence,
                        "displayed": int(confidence >= args.export_conf),
                        "x1": x1,
                        "y1": y1,
                        "x2": x2,
                        "y2": y2,
                        "width": x2 - x1,
                        "height": y2 - y1,
                    }
                )

        processed_frames += 1
        if processed_frames % 100 == 0:
            print(f"  processed sampled frames: {processed_frames}, source frame: {frame_index}/{frame_count}")
        frame_index += 1

    cap.release()
    print(f"  detections >= {args.predict_conf}: {len(rows)}")
    return rows, meta


def selected_frames_for_video(
    detections: list[dict[str, object]],
    source_video: str,
    args: argparse.Namespace,
) -> tuple[list[int], list[list[int]]]:
    frames = sorted(
        {
            int(row["frame"])
            for row in detections
            if row["source_video"] == source_video and float(row["confidence"]) >= args.export_conf
        }
    )
    segments = group_frames(frames, args.event_gap)
    selected: list[int] = []
    for segment in segments:
        selected.extend(pick_evenly(segment, min(args.frames_per_event, len(segment))))

    if args.max_frames_per_video is not None and len(selected) > args.max_frames_per_video:
        selected = pick_evenly(selected, args.max_frames_per_video)
    return selected, segments


def save_selected_frames(
    video_path: Path,
    selected_frames: list[int],
    detections: list[dict[str, object]],
    images_dir: Path,
    args: argparse.Namespace,
    meta: dict[str, int | float],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    frame_rows: list[dict[str, object]] = []
    selected_detection_rows: list[dict[str, object]] = []
    stem = safe_stem(video_path)
    fps = float(meta["fps"])

    for output_index, frame_index in enumerate(selected_frames, start=1):
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = cap.read()
        if not ok:
            print(f"  skip unreadable frame: {video_path.name}:{frame_index}")
            continue

        image_name = f"{stem}_fp_{output_index:06d}.jpg"
        image_path = images_dir / image_name
        height, width = frame.shape[:2]
        cv2.imwrite(str(image_path), frame, [cv2.IMWRITE_JPEG_QUALITY, args.jpeg_quality])

        frame_detections = [
            dict(row)
            for row in detections
            if row["source_video"] == video_path.name
            and int(row["frame"]) == frame_index
            and float(row["confidence"]) >= args.export_conf
        ]
        for row in frame_detections:
            row["image_name"] = image_name
        selected_detection_rows.extend(frame_detections)

        frame_rows.append(
            {
                "image_name": image_name,
                "original_image_name": image_name,
                "source_video": video_path.name,
                "source_frame": frame_index,
                "source_time_sec": frame_index / fps,
                "width": width,
                "height": height,
                "box_count": len(frame_detections),
                "max_confidence": max(float(row["confidence"]) for row in frame_detections),
            }
        )

    cap.release()
    return frame_rows, selected_detection_rows


def shuffle_and_rename_frames(
    frame_rows: list[dict[str, object]],
    selected_detections: list[dict[str, object]],
    images_dir: Path,
    frame_prefix: str,
    seed: int,
    shuffle: bool,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    order = list(range(len(frame_rows)))
    if shuffle:
        random.Random(seed).shuffle(order)

    updated_rows: list[dict[str, object]] = []
    image_name_mapping: dict[str, str] = {}
    temp_paths: list[tuple[Path, Path]] = []

    for temp_index, row_index in enumerate(order, start=1):
        row = dict(frame_rows[row_index])
        old_image_name = str(row["image_name"])
        temp_image_name = f"__tmp_shuffle_{temp_index:06d}.jpg"
        temp_path = images_dir / temp_image_name
        old_path = images_dir / old_image_name
        shutil.move(old_path, temp_path)
        temp_paths.append((temp_path, images_dir / f"{frame_prefix}_{temp_index:06d}.jpg"))
        image_name_mapping[old_image_name] = f"{frame_prefix}_{temp_index:06d}.jpg"

        row["original_image_name"] = old_image_name
        row["image_name"] = image_name_mapping[old_image_name]
        row["shuffle_index"] = temp_index
        updated_rows.append(row)

    for temp_path, final_path in temp_paths:
        shutil.move(temp_path, final_path)

    detection_rows_by_image: dict[str, list[dict[str, object]]] = {}
    for row in selected_detections:
        detection_rows_by_image.setdefault(str(row["image_name"]), []).append(row)

    updated_detections: list[dict[str, object]] = []
    for frame_row in updated_rows:
        original_image_name = str(frame_row["original_image_name"])
        new_image_name = str(frame_row["image_name"])
        for detection in detection_rows_by_image.get(original_image_name, []):
            updated_detection = dict(detection)
            updated_detection["original_image_name"] = original_image_name
            updated_detection["image_name"] = new_image_name
            updated_detection["shuffle_index"] = frame_row["shuffle_index"]
            updated_detections.append(updated_detection)

    return updated_rows, updated_detections


def build_cvat_xml(
    frame_rows: list[dict[str, object]],
    selected_detections: list[dict[str, object]],
    label_name: str,
    task_name: str,
) -> ET.ElementTree:
    detections_by_image: dict[str, list[dict[str, object]]] = {}
    for row in selected_detections:
        detections_by_image.setdefault(str(row["image_name"]), []).append(row)

    annotations = ET.Element("annotations")
    append_text(annotations, "version", "1.1")

    meta = ET.SubElement(annotations, "meta")
    task = ET.SubElement(meta, "task")
    append_text(task, "id", 0)
    append_text(task, "name", task_name)
    append_text(task, "size", len(frame_rows))
    append_text(task, "mode", "annotation")
    append_text(task, "overlap", 0)
    append_text(task, "bugtracker", "")
    append_text(task, "flipped", False)

    labels = ET.SubElement(task, "labels")
    label = ET.SubElement(labels, "label")
    append_text(label, "name", label_name)
    append_text(label, "color", "#ff0000")
    append_text(label, "type", "rectangle")
    ET.SubElement(label, "attributes")

    for image_id, frame_row in enumerate(frame_rows):
        image_name = str(frame_row["image_name"])
        width = float(frame_row["width"])
        height = float(frame_row["height"])
        image = ET.SubElement(
            annotations,
            "image",
            id=str(image_id),
            name=image_name,
            width=str(int(width)),
            height=str(int(height)),
        )
        for detection in detections_by_image.get(image_name, []):
            xtl = max(0.0, min(float(detection["x1"]), width - 1.0))
            ytl = max(0.0, min(float(detection["y1"]), height - 1.0))
            xbr = max(0.0, min(float(detection["x2"]), width - 1.0))
            ybr = max(0.0, min(float(detection["y2"]), height - 1.0))
            if xbr <= xtl or ybr <= ytl:
                continue
            ET.SubElement(
                image,
                "box",
                label=label_name,
                source="auto",
                occluded="0",
                xtl=f"{xtl:.2f}",
                ytl=f"{ytl:.2f}",
                xbr=f"{xbr:.2f}",
                ybr=f"{ybr:.2f}",
                z_order="0",
            )

    ET.indent(annotations, space="  ")
    return ET.ElementTree(annotations)


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    model_path = args.model.resolve()
    video_paths = [path.resolve() for path in args.videos]
    output_dir = args.output_dir.resolve()

    if args.vid_stride < 1:
        raise ValueError("--vid-stride must be >= 1")
    if args.frames_per_event < 1:
        raise ValueError("--frames-per-event must be >= 1")
    if not model_path.exists():
        raise FileNotFoundError(model_path)
    for video_path in video_paths:
        if not video_path.exists():
            raise FileNotFoundError(video_path)
    args.device = resolve_device(args.device)
    print(f"Using device: {args.device}")

    images_dir = prepare_output(output_dir, args.overwrite)
    model = YOLO(str(model_path))

    all_detections: list[dict[str, object]] = []
    frame_rows: list[dict[str, object]] = []
    selected_detection_rows: list[dict[str, object]] = []

    for video_path in video_paths:
        detections, meta = collect_detections(model, video_path, args)
        all_detections.extend(detections)

        selected_frames, segments = selected_frames_for_video(detections, video_path.name, args)
        print(
            f"  frames with detections >= {args.export_conf}: "
            f"{len({int(row['frame']) for row in detections if float(row['confidence']) >= args.export_conf})}"
        )
        print(f"  detection segments: {len(segments)}")
        print(f"  selected frames: {len(selected_frames)}")

        video_frame_rows, video_selected_detections = save_selected_frames(
            video_path=video_path,
            selected_frames=selected_frames,
            detections=detections,
            images_dir=images_dir,
            args=args,
            meta=meta,
        )
        frame_rows.extend(video_frame_rows)
        selected_detection_rows.extend(video_selected_detections)

    if not frame_rows:
        raise RuntimeError("No frames were exported. Lower --export-conf or --vid-stride.")

    frame_rows, selected_detection_rows = shuffle_and_rename_frames(
        frame_rows=frame_rows,
        selected_detections=selected_detection_rows,
        images_dir=images_dir,
        frame_prefix=args.frame_prefix,
        seed=args.seed,
        shuffle=not args.no_shuffle,
    )

    xml_tree = build_cvat_xml(frame_rows, selected_detection_rows, args.label_name, output_dir.name)
    xml_tree.write(output_dir / "annotations.xml", encoding="utf-8", xml_declaration=True)

    with ZipFile(output_dir / "images.zip", "w", compression=ZIP_STORED) as zip_file:
        for frame_row in frame_rows:
            image_path = images_dir / str(frame_row["image_name"])
            zip_file.write(image_path, arcname=str(frame_row["image_name"]))

    write_csv(output_dir / "frame_manifest.csv", frame_rows)
    write_csv(output_dir / "selected_detections.csv", selected_detection_rows)
    write_csv(output_dir / "all_detections.csv", all_detections)

    print("Done")
    print(f"Frames exported: {len(frame_rows)}")
    print(f"Boxes exported: {len(selected_detection_rows)}")
    print(f"Images zip: {output_dir / 'images.zip'}")
    print(f"Annotations XML: {output_dir / 'annotations.xml'}")
    print(f"Manifest: {output_dir / 'frame_manifest.csv'}")


if __name__ == "__main__":
    main()
