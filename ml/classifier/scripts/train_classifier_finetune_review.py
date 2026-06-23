#!/usr/bin/env python3
"""Prepare review crops and fine-tune the brand classifier."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import random
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import timm
import torch
from PIL import Image, ImageFile
from torch import nn
from torch.utils.data import DataLoader


ImageFile.LOAD_TRUNCATED_IMAGES = True
PROJECT_ROOT = Path(__file__).resolve().parents[3]
CLASSIFICATION_DATA_DIR = PROJECT_ROOT / "ml" / "data" / "classification"
CLASSIFICATION_RUNS_DIR = PROJECT_ROOT / "ml" / "runs" / "classification"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
CLASS_DIR_ALIASES = {
    "+7": "+7",
    "7": "+7",
    "plus7": "+7",
    "miranda": "miranda",
    "миранда": "miranda",
    "mts": "mts",
    "мтс": "mts",
    "other": "other",
    "другое": "other",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge reviewed crops into classifier dataset and fine-tune from best.pt."
    )
    parser.add_argument(
        "--prepare-only", action="store_true", help="Prepare data, do not train."
    )
    parser.add_argument(
        "--review-dir",
        type=Path,
        default=PROJECT_ROOT / "дообучить классификатор",
        help="Directory with class subdirectories from manual review.",
    )
    parser.add_argument(
        "--base-prepared",
        type=Path,
        default=CLASSIFICATION_DATA_DIR / "v2_ads_only" / "prepared",
        help="Existing prepared classifier dataset.",
    )
    parser.add_argument(
        "--prepared-dir",
        type=Path,
        default=CLASSIFICATION_DATA_DIR / "v2_ads_only" / "finetune_review_prepared",
        help="Merged prepared dataset output.",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=PROJECT_ROOT / "models" / "classification" / "best.pt",
        help="Existing classifier checkpoint to fine-tune from.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=CLASSIFICATION_RUNS_DIR
        / "v2_ads_only"
        / "convnext_tiny_finetune_review",
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="Rebuild --prepared-dir."
    )
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--num-workers", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20260621)
    parser.add_argument("--backbone-lr", type=float, default=1e-5)
    parser.add_argument("--finetune-head-lr", type=float, default=1e-4)
    parser.add_argument("--min-lr", type=float, default=1e-6)
    parser.add_argument("--weight-decay", type=float, default=5e-2)
    parser.add_argument("--label-smoothing", type=float, default=0.03)
    parser.add_argument("--early-stop-patience", type=int, default=5)
    parser.add_argument("--important-sample-weight", type=float, default=4.0)
    parser.add_argument("--target-aug-p", type=float, default=0.9)
    parser.add_argument("--important-aug-p", type=float, default=0.98)
    parser.add_argument("--other-aug-p", type=float, default=0.4)
    parser.add_argument("--grad-clip-norm", type=float, default=1.0)
    parser.add_argument("--no-amp", action="store_true")
    parser.add_argument("--no-balanced-sampler", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    seed_everything(args.seed)
    prepared_dir = resolve_project_path(args.prepared_dir)

    if prepared_dir.exists() and not args.overwrite:
        print(f"using existing prepared dataset: {prepared_dir}")
    else:
        prepare_finetune_dataset(args, prepared_dir)

    if args.prepare_only:
        print("prepare_only: training was not started")
        return 0

    train_classifier(args, prepared_dir)
    return 0


def resolve_project_path(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def seed_everything(seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def prepare_finetune_dataset(args: argparse.Namespace, prepared_dir: Path) -> None:
    review_dir = resolve_project_path(args.review_dir)
    base_prepared = resolve_project_path(args.base_prepared)
    if not review_dir.exists():
        raise FileNotFoundError(review_dir)
    if not (base_prepared / "manifest.csv").exists():
        raise FileNotFoundError(base_prepared / "manifest.csv")

    if prepared_dir.exists():
        if not args.overwrite:
            raise FileExistsError(
                f"{prepared_dir} already exists. Use --overwrite to rebuild it."
            )
        shutil.rmtree(prepared_dir)
    prepared_dir.mkdir(parents=True, exist_ok=True)

    base_rows = read_base_manifest(base_prepared)
    review_rows = prepare_review_images(review_dir, prepared_dir)
    rows = [*base_rows, *review_rows]

    write_manifest(prepared_dir / "manifest.csv", rows)
    write_summary(prepared_dir / "summary.json", args, base_rows, review_rows)
    print(f"base samples: {len(base_rows)}")
    print(f"review samples: {len(review_rows)}")
    print(f"prepared samples: {len(rows)}")
    print(f"prepared dir: {prepared_dir}")


def read_base_manifest(base_prepared: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with (base_prepared / "manifest.csv").open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            source_path = Path(row["file_path"])
            if not source_path.is_absolute():
                source_path = base_prepared / source_path
            rows.append(
                {
                    "split": row["split"],
                    "class": row["class"],
                    "file_path": str(source_path.resolve()),
                    "original_path": row.get("original_path", ""),
                    "original_extension": row.get(
                        "original_extension", source_path.suffix.casefold()
                    ),
                    "is_important": row.get("is_important", "0"),
                    "sha256": row.get("sha256", ""),
                    "converted_to_png": row.get("converted_to_png", "0"),
                }
            )
    return rows


def prepare_review_images(review_dir: Path, prepared_dir: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for class_dir in sorted(path for path in review_dir.iterdir() if path.is_dir()):
        class_name = normalize_class_name(class_dir.name)
        images = sorted(
            path
            for path in class_dir.iterdir()
            if path.is_file() and path.suffix.casefold() in IMAGE_EXTENSIONS
        )
        for index, source_path in enumerate(images, start=1):
            output_path = (
                prepared_dir
                / "train"
                / class_name
                / f"review_{class_name}_{index:06d}.png"
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            convert_to_png(source_path, output_path)
            rows.append(
                {
                    "split": "train",
                    "class": class_name,
                    "file_path": str(output_path.resolve()),
                    "original_path": str(source_path.resolve()),
                    "original_extension": source_path.suffix.casefold(),
                    "is_important": "1",
                    "sha256": sha256_file(source_path),
                    "converted_to_png": "1",
                }
            )
    return rows


def normalize_class_name(value: str) -> str:
    normalized = value.strip().casefold()
    if normalized not in CLASS_DIR_ALIASES:
        raise ValueError(f"Unsupported classifier class directory: {value}")
    return CLASS_DIR_ALIASES[normalized]


def convert_to_png(source_path: Path, output_path: Path) -> None:
    image = Image.open(source_path).convert("RGB")
    image.save(output_path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "split",
        "class",
        "file_path",
        "original_path",
        "original_extension",
        "is_important",
        "sha256",
        "converted_to_png",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(
    path: Path,
    args: argparse.Namespace,
    base_rows: list[dict[str, str]],
    review_rows: list[dict[str, str]],
) -> None:
    def count_by_class(rows: list[dict[str, str]]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in rows:
            counts[row["class"]] = counts.get(row["class"], 0) + 1
        return counts

    summary = {
        "base_prepared": str(resolve_project_path(args.base_prepared)),
        "review_dir": str(resolve_project_path(args.review_dir)),
        "base_samples": len(base_rows),
        "review_samples": len(review_rows),
        "total_samples": len(base_rows) + len(review_rows),
        "review_by_class": count_by_class(review_rows),
    }
    with path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def load_train_module():
    module_path = PROJECT_ROOT / "ml" / "classifier" / "scripts" / "train_convnext.py"
    spec = importlib.util.spec_from_file_location(
        "classifier_train_convnext", module_path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def train_classifier(args: argparse.Namespace, prepared_dir: Path) -> None:
    train_module = load_train_module()
    checkpoint_path = resolve_project_path(args.checkpoint)
    if not checkpoint_path.exists():
        raise FileNotFoundError(checkpoint_path)

    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    checkpoint_args = checkpoint.get("args", {})
    classes = list(checkpoint["classes"])
    model_name = checkpoint_args.get("model", "convnext_tiny.fb_in22k_ft_in1k")
    input_size = int(checkpoint_args.get("input_size", 320))

    train_args = build_train_args(args, prepared_dir, model_name, input_size)
    train_dataset, val_dataset, discovered_classes = train_module.build_datasets(
        train_args
    )
    if discovered_classes != classes:
        raise ValueError(
            f"Class mismatch. checkpoint={classes}, dataset={discovered_classes}"
        )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    use_amp = not args.no_amp and device.type == "cuda"
    if device.type == "cuda":
        torch.backends.cudnn.benchmark = True

    if args.no_balanced_sampler:
        train_sampler = None
        train_shuffle = True
    else:
        train_sampler = train_module.build_weighted_sampler(
            train_dataset, args.important_sample_weight
        )
        train_shuffle = False

    train_loader = DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        shuffle=train_shuffle,
        sampler=train_sampler,
        num_workers=args.num_workers,
        pin_memory=device.type == "cuda",
        drop_last=False,
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=args.batch_size * 2,
        shuffle=False,
        num_workers=args.num_workers,
        pin_memory=device.type == "cuda",
        drop_last=False,
    )

    model = timm.create_model(model_name, pretrained=False, num_classes=len(classes))
    model.load_state_dict(checkpoint["model_state"])
    model.to(device)
    train_module.set_backbone_trainable(model, trainable=True)

    criterion = nn.CrossEntropyLoss(label_smoothing=args.label_smoothing)
    optimizer = train_module.build_finetune_optimizer(model, train_args)
    scheduler = train_module.build_scheduler(optimizer, args.epochs, args.min_lr)
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)

    output_dir = resolve_project_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_training_config(
        output_dir,
        args,
        prepared_dir,
        classes,
        device,
        use_amp,
        train_dataset,
        val_dataset,
    )

    best_val_f1 = -math.inf
    best_val_loss = math.inf
    bad_epochs = 0
    history: list[dict[str, Any]] = []

    for epoch in range(1, args.epochs + 1):
        started = time.time()
        epoch_lr = train_module.current_lr(optimizer)
        train_metrics = train_module.run_epoch(
            model,
            train_loader,
            criterion,
            device,
            optimizer,
            scaler,
            use_amp,
            args.grad_clip_norm,
            len(classes),
        )
        with torch.no_grad():
            val_metrics = train_module.run_epoch(
                model,
                val_loader,
                criterion,
                device,
                None,
                scaler,
                use_amp,
                args.grad_clip_norm,
                len(classes),
                classes=classes,
                collect_predictions=True,
            )

        val_f1 = float(val_metrics["macro_f1"])
        val_loss = float(val_metrics["loss"])
        improved = val_f1 > best_val_f1 or (
            math.isclose(val_f1, best_val_f1) and val_loss < best_val_loss
        )
        if improved:
            best_val_f1 = val_f1
            best_val_loss = val_loss
            bad_epochs = 0
            train_module.save_checkpoint(
                output_dir,
                "best.pt",
                model,
                optimizer,
                classes,
                epoch,
                train_args,
                val_metrics,
            )
            train_module.save_confusion_matrix(
                output_dir, classes, val_metrics["confusion_matrix"]
            )
            train_module.save_classification_report(
                output_dir, classes, val_metrics["per_class"]
            )
            train_module.save_predictions(
                output_dir, "val_predictions_best.csv", val_metrics["predictions"]
            )
        else:
            bad_epochs += 1

        row = {
            "epoch": epoch,
            "stage": "review_finetune",
            "lr": epoch_lr,
            "train_loss": train_metrics["loss"],
            "train_accuracy": train_metrics["accuracy"],
            "train_macro_f1": train_metrics["macro_f1"],
            "val_loss": val_metrics["loss"],
            "val_accuracy": val_metrics["accuracy"],
            "val_macro_f1": val_metrics["macro_f1"],
        }
        history.append(row)
        train_module.save_history(output_dir, history)
        train_module.save_predictions(
            output_dir, "val_predictions_last.csv", val_metrics["predictions"]
        )
        train_module.save_checkpoint(
            output_dir,
            "last.pt",
            model,
            optimizer,
            classes,
            epoch,
            train_args,
            val_metrics,
        )
        scheduler.step()

        elapsed = time.time() - started
        print(
            f"epoch={epoch:03d} lr={row['lr']:.2e} "
            f"train_loss={row['train_loss']:.4f} train_f1={row['train_macro_f1']:.4f} "
            f"val_loss={row['val_loss']:.4f} val_f1={row['val_macro_f1']:.4f} "
            f"time={elapsed:.1f}s"
        )
        if bad_epochs >= args.early_stop_patience:
            print(
                f"Early stopping after {bad_epochs} epochs without val macro F1 improvement."
            )
            break

    print(f"Best val macro F1: {best_val_f1:.4f}")
    print(f"best checkpoint: {output_dir / 'best.pt'}")


def build_train_args(
    args: argparse.Namespace,
    prepared_dir: Path,
    model_name: str,
    input_size: int,
) -> argparse.Namespace:
    return argparse.Namespace(
        data_dir=prepared_dir,
        output_dir=resolve_project_path(args.output_dir),
        model=model_name,
        input_size=input_size,
        epochs=args.epochs,
        freeze_epochs=0,
        batch_size=args.batch_size,
        num_workers=args.num_workers,
        seed=args.seed,
        head_lr=args.finetune_head_lr,
        backbone_lr=args.backbone_lr,
        finetune_head_lr=args.finetune_head_lr,
        min_lr=args.min_lr,
        weight_decay=args.weight_decay,
        label_smoothing=args.label_smoothing,
        early_stop_patience=args.early_stop_patience,
        important_sample_weight=args.important_sample_weight,
        target_aug_p=args.target_aug_p,
        important_aug_p=args.important_aug_p,
        other_aug_p=args.other_aug_p,
        grad_clip_norm=args.grad_clip_norm,
        no_pretrained=True,
        no_amp=args.no_amp,
        no_balanced_sampler=args.no_balanced_sampler,
    )


def write_training_config(
    output_dir: Path,
    args: argparse.Namespace,
    prepared_dir: Path,
    classes: list[str],
    device: torch.device,
    use_amp: bool,
    train_dataset,
    val_dataset,
) -> None:
    config = {
        "checkpoint": str(resolve_project_path(args.checkpoint)),
        "prepared_dir": str(prepared_dir),
        "classes": classes,
        "device": str(device),
        "train_samples": len(train_dataset),
        "val_samples": len(val_dataset),
        "amp": use_amp,
        "args": {
            key: str(value) if isinstance(value, Path) else value
            for key, value in vars(args).items()
        },
    }
    with (output_dir / "config.json").open("w", encoding="utf-8") as handle:
        json.dump(config, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
