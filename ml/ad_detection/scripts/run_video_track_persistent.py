from __future__ import annotations

import argparse
import time
from pathlib import Path

import cv2
import pandas as pd
import torch
import yaml
from ultralytics import YOLO


DEFAULT_MODEL = "models/detection/trained/yolo11m_img960_antifp_cvat_corrections_ft_v1/best.pt"
DEFAULT_VIDEO = "ml/data/detection/videos/test_rotated_ccw_90.mp4"


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
        description=(
            "Run YOLO tracking on a video and draw only tracks that persist for "
            "at least N detected frames."
        )
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Path to trained YOLO .pt weights.")
    parser.add_argument("--video", default=DEFAULT_VIDEO, help="Path to input video.")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for outputs. Defaults to outputs/videos/<model_name>_<video_stem>_track_persist<N>.",
    )
    parser.add_argument("--imgsz", type=int, default=None, help="Inference image size. Defaults to train args.")
    parser.add_argument("--detect-conf", type=float, default=0.25, help="Confidence threshold used by YOLO tracker.")
    parser.add_argument("--display-conf", type=float, default=0.55, help="Minimum confidence to draw a persisted track.")
    parser.add_argument("--iou", type=float, default=0.50, help="NMS IoU threshold.")
    parser.add_argument(
        "--min-track-frames",
        type=int,
        default=10,
        help="Draw/write as shown only after a track appears in at least this many frames.",
    )
    parser.add_argument("--tracker", default="botsort.yaml", help="Ultralytics tracker config, e.g. botsort.yaml or bytetrack.yaml.")
    parser.add_argument("--line-width", type=int, default=2, help="Bounding box line width.")
    parser.add_argument("--cpu", action="store_true", help="Force CPU even if CUDA is available.")
    parser.add_argument("--no-half", action="store_true", help="Disable half precision on CUDA.")
    return parser.parse_args()


def read_train_imgsz(model_path: Path, fallback: int = 960) -> int:
    args_path = model_path.parent / "args.yaml"
    if not args_path.exists():
        return fallback
    train_args = yaml.safe_load(args_path.read_text()) or {}
    return int(train_args.get("imgsz", fallback))


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
    device = "cpu" if args.cpu or not torch.cuda.is_available() else 0
    half = device != "cpu" and not args.no_half

    run_name = f"{model_path.parent.name}_{video_path.stem}_track_persist{args.min_track_frames}"
    output_dir = (
        resolve_project_path(project_root, args.output_dir).resolve()
        if args.output_dir
        else project_root / "outputs/videos" / run_name
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    output_video = output_dir / f"{video_path.stem}_track_persist{args.min_track_frames}.mp4"
    all_csv = output_dir / "tracks_all.csv"
    shown_csv = output_dir / "tracks_shown.csv"
    summary_csv = output_dir / "tracks_summary.csv"

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration_sec = frame_count / fps if fps else 0.0
    min_track_seconds = args.min_track_frames / fps if fps else 0.0

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(output_video), fourcc, fps, (width, height))
    if not writer.isOpened():
        cap.release()
        raise RuntimeError(f"Could not create output video: {output_video}")

    print(f"project:      {project_root}")
    print(f"model:        {model_path}")
    print(f"video:        {video_path}")
    print(f"output video: {output_video}")
    print(f"all csv:      {all_csv}")
    print(f"shown csv:    {shown_csv}")
    print(f"summary csv:  {summary_csv}")
    print(f"video info:   {frame_count} frames, {fps:.2f} fps, {width}x{height}, {duration_sec / 60:.1f} min")
    print(
        f"tracking:     tracker={args.tracker}, imgsz={imgsz}, detect_conf={args.detect_conf}, "
        f"display_conf={args.display_conf}, iou={args.iou}, min_track_frames={args.min_track_frames} "
        f"({min_track_seconds:.2f} sec), device={device}, half={half}"
    )

    model = YOLO(str(model_path))
    track_lengths: dict[int, int] = {}
    track_first_frame: dict[int, int] = {}
    track_last_frame: dict[int, int] = {}
    track_max_conf: dict[int, float] = {}
    track_shown_frames: dict[int, int] = {}
    rows: list[dict] = []
    frame_idx = 0
    t0 = time.time()

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            result = model.track(
                frame,
                persist=True,
                tracker=args.tracker,
                imgsz=imgsz,
                conf=args.detect_conf,
                iou=args.iou,
                device=device,
                half=half,
                verbose=False,
            )[0]

            annotated = frame.copy()

            if result.boxes is not None and len(result.boxes) > 0:
                xyxy = result.boxes.xyxy.detach().cpu().numpy()
                confs = result.boxes.conf.detach().cpu().numpy()
                classes = result.boxes.cls.detach().cpu().numpy().astype(int)
                ids = result.boxes.id
                track_ids = ids.detach().cpu().numpy().astype(int) if ids is not None else [None] * len(xyxy)

                for det_idx, (box, score, class_id, track_id) in enumerate(zip(xyxy, confs, classes, track_ids)):
                    if track_id is None:
                        continue

                    track_id = int(track_id)
                    x1, y1, x2, y2 = box.tolist()
                    class_name = result.names.get(int(class_id), str(class_id))

                    track_lengths[track_id] = track_lengths.get(track_id, 0) + 1
                    track_first_frame.setdefault(track_id, frame_idx)
                    track_last_frame[track_id] = frame_idx
                    track_max_conf[track_id] = max(track_max_conf.get(track_id, 0.0), float(score))

                    track_age = track_lengths[track_id]
                    shown = track_age >= args.min_track_frames and float(score) >= args.display_conf
                    if shown:
                        track_shown_frames[track_id] = track_shown_frames.get(track_id, 0) + 1
                        draw_box(
                            annotated,
                            (float(x1), float(y1), float(x2), float(y2)),
                            f"{class_name} id={track_id} {float(score):.2f}",
                            args.line_width,
                        )

                    rows.append(
                        {
                            "frame": frame_idx,
                            "time_sec": frame_idx / fps if fps else 0.0,
                            "det_idx": det_idx,
                            "track_id": track_id,
                            "track_age_frames": track_age,
                            "class_id": int(class_id),
                            "class_name": class_name,
                            "conf": float(score),
                            "shown": shown,
                            "x1": float(x1),
                            "y1": float(y1),
                            "x2": float(x2),
                            "y2": float(y2),
                            "width": float(x2 - x1),
                            "height": float(y2 - y1),
                        }
                    )

            writer.write(annotated)
            frame_idx += 1

            if frame_idx % 100 == 0:
                elapsed = time.time() - t0
                proc_fps = frame_idx / elapsed if elapsed else 0.0
                print(f"processed {frame_idx}/{frame_count} frames, {proc_fps:.2f} fps")
    finally:
        cap.release()
        writer.release()

    df = pd.DataFrame(rows)
    df.to_csv(all_csv, index=False)
    shown_df = df[df["shown"]] if not df.empty else df
    shown_df.to_csv(shown_csv, index=False)

    summary_rows = []
    for track_id in sorted(track_lengths):
        first_frame = track_first_frame[track_id]
        last_frame = track_last_frame[track_id]
        detected_frames = track_lengths[track_id]
        summary_rows.append(
            {
                "track_id": track_id,
                "first_frame": first_frame,
                "last_frame": last_frame,
                "first_time_sec": first_frame / fps if fps else 0.0,
                "last_time_sec": last_frame / fps if fps else 0.0,
                "span_frames": last_frame - first_frame + 1,
                "detected_frames": detected_frames,
                "detected_seconds": detected_frames / fps if fps else 0.0,
                "max_conf": track_max_conf.get(track_id, 0.0),
                "shown_frames": track_shown_frames.get(track_id, 0),
                "kept_by_persistence": detected_frames >= args.min_track_frames,
            }
        )
    pd.DataFrame(summary_rows).to_csv(summary_csv, index=False)

    elapsed = time.time() - t0
    print(f"done in:      {elapsed / 60:.1f} min")
    print(f"frames:       {frame_idx}")
    print(f"raw rows:     {len(df)}")
    print(f"shown rows:   {len(shown_df)}")
    print(f"tracks:       {len(summary_rows)}")
    print(f"video saved:  {output_video}")
    print(f"all csv:      {all_csv}")
    print(f"shown csv:    {shown_csv}")
    print(f"summary csv:  {summary_csv}")


if __name__ == "__main__":
    main()
