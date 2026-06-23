#!/usr/bin/env python3
"""CLI entry point for the local ad visibility pipeline."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from ml.pipeline.scripts.config import (
        BusinessConfig,
        ClassificationConfig,
        DetectionConfig,
        PipelineConfig,
        RenderingConfig,
        TrackingConfig,
        default_project_root,
        resolve_project_path,
    )
    from ml.pipeline.scripts.runner import run_pipeline
else:
    from .scripts.config import (
        BusinessConfig,
        ClassificationConfig,
        DetectionConfig,
        PipelineConfig,
        RenderingConfig,
        TrackingConfig,
        default_project_root,
        resolve_project_path,
    )
    from .scripts.runner import run_pipeline


def parse_args() -> argparse.Namespace:
    project_root = default_project_root()
    parser = argparse.ArgumentParser(
        description="Run local outdoor ad visibility pipeline."
    )
    parser.add_argument(
        "--input", required=True, type=Path, help="Input image or video path."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output run directory. Defaults to outputs/pipeline/<run_id>.",
    )
    parser.add_argument(
        "--run-id", default=None, help="Run id. Defaults to timestamp + input stem."
    )
    parser.add_argument(
        "--detector-model",
        type=Path,
        default=project_root / "models/detection/best.pt",
        help="YOLO detector .pt path.",
    )
    parser.add_argument(
        "--classifier-model",
        type=Path,
        default=project_root / "models/classification/best.pt",
        help="Brand classifier .pt path.",
    )
    parser.add_argument("--frame-stride", type=int, default=10)
    parser.add_argument(
        "--device", default=None, help="Torch/Ultralytics device, e.g. cpu or 0."
    )
    parser.add_argument(
        "--brand-overrides",
        type=Path,
        default=None,
        help="CSV with manual brand overrides by track_id or crop_name.",
    )
    parser.add_argument("--detector-conf-min", type=float, default=0.50)
    parser.add_argument("--detector-imgsz", type=int, default=960)
    parser.add_argument("--detector-iou", type=float, default=0.50)
    parser.add_argument("--min-detection-width", type=int, default=48)
    parser.add_argument("--min-detection-height", type=int, default=40)
    parser.add_argument("--min-detection-area-ratio", type=float, default=0.001)
    parser.add_argument("--min-detection-aspect-ratio", type=float, default=0.25)
    parser.add_argument("--max-detection-aspect-ratio", type=float, default=8.0)
    parser.add_argument("--min-track-detections", type=int, default=2)
    parser.add_argument("--min-track-frame-span", type=int, default=10)
    parser.add_argument("--best-crops-per-object", type=int, default=3)
    parser.add_argument("--object-merge-max-gap-frames", type=int, default=90)
    parser.add_argument("--object-merge-min-iou", type=float, default=0.02)
    parser.add_argument("--object-merge-max-center-distance", type=float, default=0.18)
    parser.add_argument("--object-merge-max-area-ratio", type=float, default=5.0)
    parser.add_argument("--object-merge-max-aspect-ratio", type=float, default=3.0)
    parser.add_argument("--business-min-object-detections", type=int, default=3)
    parser.add_argument("--business-min-visible-duration-sec", type=float, default=0.50)
    parser.add_argument("--render-gap-fill-max-sec", type=float, default=0.35)
    parser.add_argument(
        "--save-annotated-frames",
        action="store_true",
        help="Save annotated frame JPGs.",
    )
    return parser.parse_args()


def build_config(args: argparse.Namespace) -> PipelineConfig:
    project_root = default_project_root()
    input_path = resolve_project_path(project_root, args.input)
    run_id = args.run_id or default_run_id(input_path)
    output_dir = (
        resolve_project_path(project_root, args.output_dir)
        if args.output_dir
        else project_root / "outputs/pipeline" / run_id
    )
    return PipelineConfig(
        input_path=input_path,
        output_dir=output_dir,
        detector_model_path=resolve_project_path(project_root, args.detector_model),
        classifier_model_path=resolve_project_path(project_root, args.classifier_model),
        brand_overrides_path=(
            resolve_project_path(project_root, args.brand_overrides)
            if args.brand_overrides
            else None
        ),
        run_id=run_id,
        frame_stride=args.frame_stride,
        device=args.device,
        detection=DetectionConfig(
            confidence_min=args.detector_conf_min,
            image_size=args.detector_imgsz,
            iou=args.detector_iou,
            min_width=args.min_detection_width,
            min_height=args.min_detection_height,
            min_area_ratio=args.min_detection_area_ratio,
            min_aspect_ratio=args.min_detection_aspect_ratio,
            max_aspect_ratio=args.max_detection_aspect_ratio,
        ),
        classification=ClassificationConfig(
            best_crops_per_object=args.best_crops_per_object,
        ),
        tracking=TrackingConfig(
            min_detections=args.min_track_detections,
            min_frame_span=args.min_track_frame_span,
            object_merge_max_gap_frames=args.object_merge_max_gap_frames,
            object_merge_min_iou=args.object_merge_min_iou,
            object_merge_max_center_distance=args.object_merge_max_center_distance,
            object_merge_max_area_ratio=args.object_merge_max_area_ratio,
            object_merge_max_aspect_ratio=args.object_merge_max_aspect_ratio,
        ),
        business=BusinessConfig(
            min_object_detections=args.business_min_object_detections,
            min_visible_duration_sec=args.business_min_visible_duration_sec,
        ),
        rendering=RenderingConfig(
            gap_fill_max_sec=args.render_gap_fill_max_sec,
            save_annotated_frames=args.save_annotated_frames,
        ),
    )


def default_run_id(input_path: Path) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{timestamp}_{input_path.stem}"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args()
    config = build_config(args)
    run_pipeline(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
