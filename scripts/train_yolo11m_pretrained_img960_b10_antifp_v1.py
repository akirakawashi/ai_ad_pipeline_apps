#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(PROJECT_ROOT / ".cache/matplotlib"))

from ultralytics import YOLO


DATA_YAML = PROJECT_ROOT / "data/yolo/ad_surface_full_v1/data.yaml"
MODEL_SOURCE = PROJECT_ROOT / "models/pretrained/yolo11m.pt"
RUN_PROJECT = PROJECT_ROOT / "runs/detect/ad_surface_full_v1"
RUN_NAME = "yolo11m_pretrained_img960_b10_antifp_full_v1"
EXPORT_DIR = PROJECT_ROOT / "models/trained/yolo11m_pretrained_img960_b10_antifp_full_v1"


def parse_batch(value: str) -> int | float:
    parsed = float(value)
    return int(parsed) if parsed.is_integer() else parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train YOLO11m pretrained anti-false-positive run on ad_surface_full_v1.")
    parser.add_argument("--data", type=Path, default=DATA_YAML)
    parser.add_argument("--model", type=Path, default=MODEL_SOURCE)
    parser.add_argument("--project", type=Path, default=RUN_PROJECT)
    parser.add_argument("--name", default=RUN_NAME)
    parser.add_argument("--export-dir", type=Path, default=EXPORT_DIR)
    parser.add_argument("--epochs", type=int, default=150)
    parser.add_argument("--imgsz", type=int, default=960)
    parser.add_argument("--batch", type=parse_batch, default=10)
    parser.add_argument("--device", default="0")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--patience", type=int, default=35)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--lr0", type=float, default=0.002)
    parser.add_argument("--lrf", type=float, default=0.01)
    parser.add_argument("--overwrite-export", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def copy_training_artifacts(run_dir: Path, export_dir: Path, overwrite: bool) -> None:
    if export_dir.exists():
        if not overwrite:
            raise FileExistsError(f"{export_dir} already exists. Use --overwrite-export to replace it.")
        shutil.rmtree(export_dir)

    export_dir.mkdir(parents=True, exist_ok=True)
    for source_path in [
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
    ]:
        if source_path.exists():
            shutil.copy2(source_path, export_dir / source_path.name)


def main() -> None:
    args = parse_args()
    data_yaml = args.data.resolve()
    model_source = args.model.resolve()
    run_project = args.project.resolve()
    export_dir = args.export_dir.resolve()

    config = {
        "hypothesis": "YOLO11m pretrained, lower image size and larger batch to reduce texture-driven false positives",
        "data": str(data_yaml),
        "model": str(model_source),
        "project": str(run_project),
        "name": args.name,
        "export_dir": str(export_dir),
        "epochs": args.epochs,
        "imgsz": args.imgsz,
        "batch": args.batch,
        "device": args.device,
        "workers": args.workers,
        "patience": args.patience,
        "lr0": args.lr0,
        "lrf": args.lrf,
    }
    for key, value in config.items():
        print(f"{key}: {value}")
    if args.dry_run:
        return

    if not data_yaml.exists():
        raise FileNotFoundError(data_yaml)
    if not model_source.exists():
        raise FileNotFoundError(model_source)

    model = YOLO(str(model_source))
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
        cos_lr=True,
        warmup_epochs=3.0,
        close_mosaic=15,
        cache=False,
        amp=True,
        plots=True,
        val=True,
        resume=False,
    )

    run_dir = Path(model.trainer.save_dir).resolve()
    copy_training_artifacts(run_dir, export_dir, args.overwrite_export)
    print(f"Training run finished: {run_dir}")
    print(f"Artifacts copied to: {export_dir}")


if __name__ == "__main__":
    main()
