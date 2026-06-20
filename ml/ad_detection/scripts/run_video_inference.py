from __future__ import annotations

import argparse
from dataclasses import dataclass
import time
from pathlib import Path
from typing import Any

import cv2
import pandas as pd
import torch
import yaml
from ultralytics import YOLO


DEFAULT_MODEL = "models/detection/trained/yolo11m_pretrained_img960_b10_antifp_full_v1/best.pt"
DEFAULT_VIDEO = "ml/data/detection/videos/test_rotated_ccw_90.mp4"


@dataclass
class DetectionEvent:
    event_id: int
    class_id: int
    class_name: str
    first_frame: int
    last_frame: int
    best_frame: int
    best_conf: float
    best_box: tuple[float, float, float, float]
    hits: int
    best_image: Any


def find_project_root(start: Path | None = None) -> Path:
    start = (start or Path.cwd()).resolve()
    for path in (start, *start.parents):
        if (path / "pyproject.toml").exists() and (path / "ml/ad_detection").exists():
            return path
    raise FileNotFoundError("Could not find ad_detection project root")


def resolve_project_path(project_root: Path, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return project_root / path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run trained YOLO ad detector on a video and save annotated video plus detections CSV."
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Path to trained YOLO .pt weights.")
    parser.add_argument("--video", default=DEFAULT_VIDEO, help="Path to input video.")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for output files. Defaults to outputs/videos/<model_name>_<video_stem>.",
    )
    parser.add_argument("--imgsz", type=int, default=None, help="Inference image size. Defaults to train args.")
    parser.add_argument("--detect-conf", type=float, default=0.25, help="Confidence threshold used by YOLO.")
    parser.add_argument(
        "--display-conf",
        type=float,
        default=0.55,
        help="Minimum confidence to draw a box on the output video. Lower detections still go to CSV.",
    )
    parser.add_argument("--iou", type=float, default=0.50, help="NMS IoU threshold.")
    parser.add_argument(
        "--frame-stride",
        type=int,
        default=1,
        help="Run detector each N frames. Skipped frames reuse no boxes and are still written to video.",
    )
    parser.add_argument("--line-width", type=int, default=2, help="Bounding box line width.")
    parser.add_argument(
        "--event-conf",
        type=float,
        default=None,
        help="Confidence threshold for saving review frames. Defaults to --display-conf.",
    )
    parser.add_argument(
        "--event-gap-sec",
        type=float,
        default=2.0,
        help="Merge flickering detections into one event if they reappear within this many seconds.",
    )
    parser.add_argument(
        "--event-iou",
        type=float,
        default=0.10,
        help="Merge detections into one event when boxes overlap by at least this IoU.",
    )
    parser.add_argument(
        "--event-center-dist",
        type=float,
        default=0.25,
        help="Merge detections when normalized center distance is below this value.",
    )
    parser.add_argument(
        "--skip-frame-mining",
        action="store_true",
        help="Do not save one representative frame per high-confidence detection event.",
    )
    parser.add_argument("--no-save-video", action="store_true", help="Do not write annotated output video.")
    parser.add_argument("--cpu", action="store_true", help="Force CPU even if CUDA is available.")
    parser.add_argument("--no-half", action="store_true", help="Disable half precision on CUDA.")
    return parser.parse_args()


def read_train_imgsz(model_path: Path, fallback: int = 960) -> int:
    args_path = model_path.parent / "args.yaml"
    if not args_path.exists():
        return fallback
    train_args = yaml.safe_load(args_path.read_text()) or {}
    return int(train_args.get("imgsz", fallback))


def sanitize_name(value: str) -> str:
    allowed = []
    for char in value.lower():
        if char.isalnum():
            allowed.append(char)
        elif char in ("-", "_"):
            allowed.append(char)
        else:
            allowed.append("_")
    return "".join(allowed).strip("_") or "class"


def clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def bbox_iou(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    inter_w = max(0.0, ix2 - ix1)
    inter_h = max(0.0, iy2 - iy1)
    inter = inter_w * inter_h
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    if union <= 0:
        return 0.0
    return inter / union


def normalized_center_distance(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
    image_width: int,
    image_height: int,
) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    acx = (ax1 + ax2) / 2.0
    acy = (ay1 + ay2) / 2.0
    bcx = (bx1 + bx2) / 2.0
    bcy = (by1 + by2) / 2.0
    diagonal = max((image_width**2 + image_height**2) ** 0.5, 1.0)
    return (((acx - bcx) ** 2 + (acy - bcy) ** 2) ** 0.5) / diagonal


def match_event(
    events: list[DetectionEvent],
    class_id: int,
    frame_idx: int,
    box: tuple[float, float, float, float],
    max_gap_frames: int,
    min_iou: float,
    max_center_dist: float,
    image_width: int,
    image_height: int,
) -> DetectionEvent | None:
    best_event = None
    best_score = -1.0
    for event in events:
        if event.class_id != class_id:
            continue
        gap = frame_idx - event.last_frame
        if gap < 0 or gap > max_gap_frames:
            continue

        iou = bbox_iou(box, event.best_box)
        center_dist = normalized_center_distance(box, event.best_box, image_width, image_height)
        if iou < min_iou and center_dist > max_center_dist:
            continue

        score = iou + (1.0 - center_dist)
        if score > best_score:
            best_score = score
            best_event = event
    return best_event


def yolo_label_line(
    class_id: int,
    box: tuple[float, float, float, float],
    image_width: int,
    image_height: int,
) -> str:
    x1, y1, x2, y2 = box
    x1 = clip(x1, 0.0, float(image_width))
    y1 = clip(y1, 0.0, float(image_height))
    x2 = clip(x2, 0.0, float(image_width))
    y2 = clip(y2, 0.0, float(image_height))
    x_center = ((x1 + x2) / 2.0) / image_width
    y_center = ((y1 + y2) / 2.0) / image_height
    width = max(0.0, x2 - x1) / image_width
    height = max(0.0, y2 - y1) / image_height
    return f"{class_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}"


def draw_box(
    frame,
    box: tuple[float, float, float, float],
    label: str,
    line_width: int,
) -> None:
    x1, y1, x2, y2 = box
    p1 = (int(round(x1)), int(round(y1)))
    p2 = (int(round(x2)), int(round(y2)))
    color = (0, 0, 255)
    cv2.rectangle(frame, p1, p2, color, line_width)

    text_size, baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
    tx1, ty1 = p1
    ty1 = max(ty1, text_size[1] + baseline + 4)
    cv2.rectangle(
        frame,
        (tx1, ty1 - text_size[1] - baseline - 4),
        (tx1 + text_size[0] + 6, ty1),
        color,
        -1,
    )
    cv2.putText(
        frame,
        label,
        (tx1 + 3, ty1 - baseline - 2),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )


def main() -> None:
    args = parse_args()
    project_root = find_project_root(Path(__file__))

    model_path = resolve_project_path(project_root, args.model).resolve()
    video_path = resolve_project_path(project_root, args.video).resolve()
    if not model_path.exists():
        raise FileNotFoundError(f"Model was not found: {model_path}")
    if not video_path.exists():
        raise FileNotFoundError(f"Video was not found: {video_path}")

    imgsz = args.imgsz if args.imgsz is not None else read_train_imgsz(model_path)
    event_conf = args.display_conf if args.event_conf is None else args.event_conf
    device = "cpu" if args.cpu or not torch.cuda.is_available() else 0
    half = device != "cpu" and not args.no_half

    run_name = f"{model_path.parent.name}_{video_path.stem}"
    output_dir = (
        resolve_project_path(project_root, args.output_dir).resolve()
        if args.output_dir
        else project_root / "outputs/videos" / run_name
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    output_video = output_dir / f"{video_path.stem}_pred.mp4"
    output_csv = output_dir / "detections.csv"
    mining_dir = output_dir / "mined_frames"
    mining_images_dir = mining_dir / "images"
    mining_previews_dir = mining_dir / "previews"
    mining_labels_dir = mining_dir / "labels_pred_yolo"
    mining_events_csv = mining_dir / "events.csv"
    mining_classes_path = mining_dir / "classes.txt"

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration_sec = frame_count / fps if fps else 0.0
    event_gap_frames = int(round(args.event_gap_sec * fps))

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = None
    if not args.no_save_video:
        writer = cv2.VideoWriter(str(output_video), fourcc, fps, (width, height))
        if not writer.isOpened():
            cap.release()
            raise RuntimeError(f"Could not create output video: {output_video}")

    print(f"project:      {project_root}")
    print(f"model:        {model_path}")
    print(f"video:        {video_path}")
    print(f"output video: {output_video if writer is not None else 'disabled'}")
    print(f"output csv:   {output_csv}")
    print(f"mined frames: {mining_dir if not args.skip_frame_mining else 'disabled'}")
    print(f"video info:   {frame_count} frames, {fps:.2f} fps, {width}x{height}, {duration_sec / 60:.1f} min")
    print(
        f"inference:    imgsz={imgsz}, detect_conf={args.detect_conf}, "
        f"display_conf={args.display_conf}, iou={args.iou}, device={device}, half={half}"
    )
    print(
        f"mining:       event_conf={event_conf}, event_gap_sec={args.event_gap_sec}, "
        f"event_gap_frames={event_gap_frames}, event_iou={args.event_iou}, "
        f"event_center_dist={args.event_center_dist}"
    )

    model = YOLO(str(model_path))
    rows: list[dict] = []
    events: list[DetectionEvent] = []
    mining_detections_by_frame: dict[int, list[dict]] = {}
    frame_idx = 0
    t0 = time.time()

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            annotated = frame.copy()
            should_detect = frame_idx % args.frame_stride == 0
            current_frame_mining_detections: list[dict] = []

            if should_detect:
                result = model.predict(
                    frame,
                    imgsz=imgsz,
                    conf=args.detect_conf,
                    iou=args.iou,
                    device=device,
                    half=half,
                    verbose=False,
                )[0]

                if result.boxes is not None and len(result.boxes) > 0:
                    xyxy = result.boxes.xyxy.detach().cpu().numpy()
                    confs = result.boxes.conf.detach().cpu().numpy()
                    classes = result.boxes.cls.detach().cpu().numpy().astype(int)

                    for det_idx, (box, score, class_id) in enumerate(zip(xyxy, confs, classes)):
                        x1, y1, x2, y2 = box.tolist()
                        box_tuple = (float(x1), float(y1), float(x2), float(y2))
                        class_name = result.names.get(int(class_id), str(class_id))
                        shown = float(score) >= args.display_conf
                        if shown:
                            draw_box(
                                annotated,
                                box_tuple,
                                f"{class_name} {float(score):.2f}",
                                args.line_width,
                            )

                        event_id = None
                        if not args.skip_frame_mining and float(score) >= event_conf:
                            event = match_event(
                                events,
                                int(class_id),
                                frame_idx,
                                box_tuple,
                                event_gap_frames,
                                args.event_iou,
                                args.event_center_dist,
                                width,
                                height,
                            )
                            if event is None:
                                event = DetectionEvent(
                                    event_id=len(events) + 1,
                                    class_id=int(class_id),
                                    class_name=class_name,
                                    first_frame=frame_idx,
                                    last_frame=frame_idx,
                                    best_frame=frame_idx,
                                    best_conf=float(score),
                                    best_box=box_tuple,
                                    hits=1,
                                    best_image=frame.copy(),
                                )
                                events.append(event)
                            else:
                                event.last_frame = frame_idx
                                event.hits += 1
                                if float(score) > event.best_conf:
                                    event.best_frame = frame_idx
                                    event.best_conf = float(score)
                                    event.best_box = box_tuple
                                    event.best_image = frame.copy()
                            event_id = event.event_id

                            current_frame_mining_detections.append(
                                {
                                    "class_id": int(class_id),
                                    "class_name": class_name,
                                    "conf": float(score),
                                    "box": box_tuple,
                                }
                            )

                        rows.append(
                            {
                                "frame": frame_idx,
                                "time_sec": frame_idx / fps if fps else 0.0,
                                "det_idx": det_idx,
                                "class_id": int(class_id),
                                "class_name": class_name,
                                "conf": float(score),
                                "shown": shown,
                                "event_id": event_id,
                                "x1": float(x1),
                                "y1": float(y1),
                                "x2": float(x2),
                                "y2": float(y2),
                                "width": float(x2 - x1),
                                "height": float(y2 - y1),
                            }
                        )

                if current_frame_mining_detections:
                    mining_detections_by_frame[frame_idx] = current_frame_mining_detections

            if writer is not None:
                writer.write(annotated)
            frame_idx += 1

            if frame_idx % 100 == 0:
                elapsed = time.time() - t0
                proc_fps = frame_idx / elapsed if elapsed else 0.0
                print(f"processed {frame_idx}/{frame_count} frames, {proc_fps:.2f} fps")
    finally:
        cap.release()
        if writer is not None:
            writer.release()

    df = pd.DataFrame(rows)
    df.to_csv(output_csv, index=False)

    event_rows: list[dict] = []
    if not args.skip_frame_mining:
        mining_images_dir.mkdir(parents=True, exist_ok=True)
        mining_previews_dir.mkdir(parents=True, exist_ok=True)
        mining_labels_dir.mkdir(parents=True, exist_ok=True)

        model_names = getattr(model, "names", {}) or {}
        if isinstance(model_names, dict):
            class_names = [str(model_names[key]) for key in sorted(model_names)]
        else:
            class_names = [str(name) for name in model_names]
        mining_classes_path.write_text("\n".join(class_names) + "\n")

        for event in events:
            stem = (
                f"event_{event.event_id:04d}_frame_{event.best_frame:06d}_"
                f"{sanitize_name(event.class_name)}_{event.best_conf:.2f}"
            )
            image_path = mining_images_dir / f"{stem}.jpg"
            preview_path = mining_previews_dir / f"{stem}.jpg"
            label_path = mining_labels_dir / f"{stem}.txt"

            cv2.imwrite(str(image_path), event.best_image)

            preview = event.best_image.copy()
            label_lines = []
            frame_detections = mining_detections_by_frame.get(event.best_frame, [])
            for detection in frame_detections:
                draw_box(
                    preview,
                    detection["box"],
                    f"{detection['class_name']} {detection['conf']:.2f}",
                    args.line_width,
                )
                label_lines.append(
                    yolo_label_line(detection["class_id"], detection["box"], width, height)
                )

            cv2.imwrite(str(preview_path), preview)
            label_path.write_text("\n".join(label_lines) + ("\n" if label_lines else ""))

            x1, y1, x2, y2 = event.best_box
            event_rows.append(
                {
                    "event_id": event.event_id,
                    "class_id": event.class_id,
                    "class_name": event.class_name,
                    "first_frame": event.first_frame,
                    "last_frame": event.last_frame,
                    "best_frame": event.best_frame,
                    "best_time_sec": event.best_frame / fps if fps else 0.0,
                    "best_conf": event.best_conf,
                    "hits": event.hits,
                    "image": str(image_path.relative_to(mining_dir)),
                    "preview": str(preview_path.relative_to(mining_dir)),
                    "pred_label": str(label_path.relative_to(mining_dir)),
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                    "width": x2 - x1,
                    "height": y2 - y1,
                }
            )

        pd.DataFrame(event_rows).to_csv(mining_events_csv, index=False)

    elapsed = time.time() - t0
    print(f"done in:      {elapsed / 60:.1f} min")
    print(f"frames:       {frame_idx}")
    print(f"detections:   {len(df)}")
    if writer is not None:
        print(f"video saved:  {output_video}")
    print(f"csv saved:    {output_csv}")
    if not args.skip_frame_mining:
        print(f"events saved: {len(event_rows)}")
        print(f"frames dir:   {mining_images_dir}")
        print(f"previews dir: {mining_previews_dir}")
        print(f"labels dir:   {mining_labels_dir}")
        print(f"events csv:   {mining_events_csv}")

    if not df.empty:
        summary = (
            df.groupby("class_name")
            .agg(
                detections=("conf", "size"),
                frames=("frame", "nunique"),
                mean_conf=("conf", "mean"),
                max_conf=("conf", "max"),
            )
            .sort_values("detections", ascending=False)
        )
        print(summary)


if __name__ == "__main__":
    main()
