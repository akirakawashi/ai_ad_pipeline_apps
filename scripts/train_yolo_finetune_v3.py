#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(PROJECT_ROOT / ".cache/matplotlib"))

from ultralytics import YOLO


DEFAULT_DATA_YAML = PROJECT_ROOT / "data/yolo/ad_surface_v3_finetune/data.yaml"
DEFAULT_START_WEIGHTS = PROJECT_ROOT / "models/trained/yolo11x_scratch_img1280/best.pt"
DEFAULT_RUN_PROJECT = PROJECT_ROOT / "runs/detect/ad_surface_v3"
DEFAULT_RUN_NAME = "yolo11x_finetune_hard_negatives_v1"
DEFAULT_EXPORT_DIR = PROJECT_ROOT / "models/trained/yolo11x_finetune_hard_negatives_v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fine-tune YOLO11x from checked ad-surface weights.")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_YAML)
    parser.add_argument("--weights", type=Path, default=DEFAULT_START_WEIGHTS)
    parser.add_argument("--project", type=Path, default=DEFAULT_RUN_PROJECT)
    parser.add_argument("--name", default=DEFAULT_RUN_NAME)
    parser.add_argument("--export-dir", type=Path, default=DEFAULT_EXPORT_DIR)
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--imgsz", type=int, default=1280)
    parser.add_argument("--batch", type=int, default=2)
    parser.add_argument("--device", default="0")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--patience", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--lr0", type=float, default=0.002)
    parser.add_argument("--lrf", type=float, default=0.01)
    parser.add_argument("--overwrite-export", action="store_true")
    return parser.parse_args()


def copy_training_artifacts(run_dir: Path, export_dir: Path, overwrite: bool) -> None:
    if export_dir.exists():
        if not overwrite:
            raise FileExistsError(
                f"{export_dir} already exists. Re-run with --overwrite-export to replace exported artifacts."
            )
        shutil.rmtree(export_dir)

    export_dir.mkdir(parents=True, exist_ok=True)
    candidates = [
        run_dir / "weights/best.pt",
        run_dir / "weights/last.pt",
        run_dir / "args.yaml",
        run_dir / "results.csv",
        run_dir / "results.png",
        run_dir / "confusion_matrix.png",
        run_dir / "confusion_matrix_normalized.png",
        run_dir / "PR_curve.png",
        run_dir / "P_curve.png",
        run_dir / "R_curve.png",
        run_dir / "F1_curve.png",
    ]

    copied = 0
    for source_path in candidates:
        if source_path.exists():
            shutil.copy2(source_path, export_dir / source_path.name)
            copied += 1

    print(f"Copied {copied} artifacts to: {export_dir}")


def main() -> None:
    args = parse_args()
    data_yaml = args.data.resolve()
    weights = args.weights.resolve()
    run_project = args.project.resolve()
    export_dir = args.export_dir.resolve()

    if not data_yaml.exists():
        raise FileNotFoundError(f"Dataset yaml not found: {data_yaml}")
    if not weights.exists():
        raise FileNotFoundError(f"Start weights not found: {weights}")

    print(f"Fine-tuning from weights: {weights}")
    print(f"Dataset: {data_yaml}")
    print(f"Run output: {run_project / args.name}")

    model = YOLO(str(weights))
    model.train(
        data=str(data_yaml),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        workers=args.workers,
        patience=args.patience,
        seed=args.seed,
        deterministic=True,
        project=str(run_project),
        name=args.name,
        exist_ok=False,
        pretrained=True,
        optimizer="auto",
        lr0=args.lr0,
        lrf=args.lrf,
        warmup_epochs=2.0,
        close_mosaic=10,
        cache=False,
        plots=True,
        val=True,
        resume=False,
    )

    run_dir = Path(model.trainer.save_dir).resolve()
    copy_training_artifacts(run_dir, export_dir, args.overwrite_export)
    print(f"Training run finished: {run_dir}")


if __name__ == "__main__":
    main()
