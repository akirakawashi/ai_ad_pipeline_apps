#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import timm
import torch
from PIL import Image, ImageFile, ImageOps
from torch import nn
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
from torchvision import transforms


ImageFile.LOAD_TRUNCATED_IMAGES = True
PROJECT_ROOT = Path(__file__).resolve().parents[3]
CLASSIFICATION_DATA_DIR = PROJECT_ROOT / "ml" / "data" / "classification"
CLASSIFICATION_RUNS_DIR = PROJECT_ROOT / "ml" / "runs" / "classification"


@dataclass(frozen=True)
class Sample:
    file_path: Path
    class_name: str
    label: int
    is_important: bool


class ResizePad:
    def __init__(self, size: int, fill: tuple[int, int, int] = (0, 0, 0)) -> None:
        self.size = size
        self.fill = fill

    def __call__(self, image: Image.Image) -> Image.Image:
        contained = ImageOps.contain(image, (self.size, self.size), Image.Resampling.BICUBIC)
        canvas = Image.new("RGB", (self.size, self.size), self.fill)
        offset = ((self.size - contained.width) // 2, (self.size - contained.height) // 2)
        canvas.paste(contained, offset)
        return canvas


class PreparedImageDataset(Dataset):
    def __init__(
        self,
        root_dir: Path,
        manifest_path: Path,
        split: str,
        class_to_idx: dict[str, int],
        target_transform: transforms.Compose,
        important_transform: transforms.Compose,
        other_transform: transforms.Compose,
        val_transform: transforms.Compose,
    ) -> None:
        self.root_dir = root_dir
        self.split = split
        self.class_to_idx = class_to_idx
        self.target_transform = target_transform
        self.important_transform = important_transform
        self.other_transform = other_transform
        self.val_transform = val_transform
        self.samples = self._read_samples(manifest_path)

    def _read_samples(self, manifest_path: Path) -> list[Sample]:
        samples: list[Sample] = []
        with manifest_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if row["split"] != self.split:
                    continue
                class_name = row["class"]
                samples.append(
                    Sample(
                        file_path=Path(row["file_path"]),
                        class_name=class_name,
                        label=self.class_to_idx[class_name],
                        is_important=row["is_important"] == "1",
                    )
                )
        return samples

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int) -> dict[str, Any]:
        sample = self.samples[index]
        image = Image.open(self.root_dir / sample.file_path).convert("RGB")

        if self.split == "val":
            image = self.val_transform(image)
        elif sample.is_important:
            image = self.important_transform(image)
        elif sample.class_name == "other":
            image = self.other_transform(image)
        else:
            image = self.target_transform(image)

        return {
            "image": image,
            "label": sample.label,
            "class_name": sample.class_name,
            "path": str(sample.file_path),
            "is_important": sample.is_important,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train ConvNeXt classifier.")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=CLASSIFICATION_DATA_DIR / "v2_ads_only" / "prepared",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=CLASSIFICATION_RUNS_DIR / "v2_ads_only" / "convnext_tiny",
    )
    parser.add_argument("--model", default="convnext_tiny.fb_in22k_ft_in1k")
    parser.add_argument("--input-size", type=int, default=320)
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--freeze-epochs", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--num-workers", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20260617)
    parser.add_argument("--head-lr", type=float, default=1e-3)
    parser.add_argument("--backbone-lr", type=float, default=2e-5)
    parser.add_argument("--finetune-head-lr", type=float, default=2e-4)
    parser.add_argument("--min-lr", type=float, default=1e-6)
    parser.add_argument("--weight-decay", type=float, default=5e-2)
    parser.add_argument("--label-smoothing", type=float, default=0.05)
    parser.add_argument("--early-stop-patience", type=int, default=10)
    parser.add_argument("--important-sample-weight", type=float, default=1.0)
    parser.add_argument("--target-aug-p", type=float, default=0.8)
    parser.add_argument("--important-aug-p", type=float, default=0.95)
    parser.add_argument("--other-aug-p", type=float, default=0.4)
    parser.add_argument("--grad-clip-norm", type=float, default=1.0)
    parser.add_argument("--no-pretrained", action="store_true")
    parser.add_argument("--no-amp", action="store_true")
    parser.add_argument("--no-balanced-sampler", action="store_true")
    return parser.parse_args()


def seed_everything(seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def jsonable_args(args: argparse.Namespace) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in vars(args).items():
        result[key] = str(value) if isinstance(value, Path) else value
    return result


def discover_classes(manifest_path: Path) -> list[str]:
    classes: set[str] = set()
    with manifest_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            classes.add(row["class"])
    return sorted(classes)


def build_train_transform(size: int, aug_p: float, erase_p: float) -> transforms.Compose:
    return transforms.Compose(
        [
            transforms.RandomApply(
                [
                    transforms.ColorJitter(
                        brightness=0.22,
                        contrast=0.22,
                        saturation=0.12,
                        hue=0.015,
                    )
                ],
                p=aug_p,
            ),
            transforms.RandomApply(
                [transforms.GaussianBlur(kernel_size=3, sigma=(0.1, 1.2))],
                p=min(0.2, aug_p),
            ),
            transforms.RandomApply(
                [transforms.RandomPerspective(distortion_scale=0.08, p=1.0)],
                p=min(0.25, aug_p),
            ),
            transforms.RandomApply(
                [
                    transforms.RandomAffine(
                        degrees=5,
                        translate=(0.03, 0.03),
                        scale=(0.92, 1.08),
                        shear=(-3, 3, -2, 2),
                        fill=(0, 0, 0),
                        interpolation=transforms.InterpolationMode.BICUBIC,
                    )
                ],
                p=aug_p,
            ),
            ResizePad(size),
            transforms.ToTensor(),
            transforms.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
            transforms.RandomErasing(
                p=erase_p,
                scale=(0.01, 0.06),
                ratio=(0.3, 3.3),
                value="random",
            ),
        ]
    )


def build_val_transform(size: int) -> transforms.Compose:
    return transforms.Compose(
        [
            ResizePad(size),
            transforms.ToTensor(),
            transforms.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
        ]
    )


def build_datasets(args: argparse.Namespace) -> tuple[PreparedImageDataset, PreparedImageDataset, list[str]]:
    manifest_path = args.data_dir / "manifest.csv"
    classes = discover_classes(manifest_path)
    class_to_idx = {class_name: index for index, class_name in enumerate(classes)}

    target_transform = build_train_transform(args.input_size, args.target_aug_p, erase_p=0.08)
    important_transform = build_train_transform(args.input_size, args.important_aug_p, erase_p=0.12)
    other_transform = build_train_transform(args.input_size, args.other_aug_p, erase_p=0.06)
    val_transform = build_val_transform(args.input_size)

    train_dataset = PreparedImageDataset(
        args.data_dir,
        manifest_path,
        "train",
        class_to_idx,
        target_transform,
        important_transform,
        other_transform,
        val_transform,
    )
    val_dataset = PreparedImageDataset(
        args.data_dir,
        manifest_path,
        "val",
        class_to_idx,
        target_transform,
        important_transform,
        other_transform,
        val_transform,
    )
    return train_dataset, val_dataset, classes


def build_weighted_sampler(dataset: PreparedImageDataset, important_weight: float) -> WeightedRandomSampler:
    class_counts: dict[int, int] = {}
    for sample in dataset.samples:
        class_counts[sample.label] = class_counts.get(sample.label, 0) + 1

    weights: list[float] = []
    for sample in dataset.samples:
        weight = 1.0 / class_counts[sample.label]
        if sample.is_important:
            weight *= important_weight
        weights.append(weight)

    return WeightedRandomSampler(weights, num_samples=len(weights), replacement=True)


def get_head_parameters(model: nn.Module) -> set[int]:
    classifier = model.get_classifier()
    return {id(parameter) for parameter in classifier.parameters()}


def set_backbone_trainable(model: nn.Module, trainable: bool) -> None:
    head_parameter_ids = get_head_parameters(model)
    for parameter in model.parameters():
        parameter.requires_grad = trainable or id(parameter) in head_parameter_ids


def build_head_optimizer(model: nn.Module, args: argparse.Namespace) -> torch.optim.Optimizer:
    classifier = model.get_classifier()
    return torch.optim.AdamW(
        classifier.parameters(),
        lr=args.head_lr,
        weight_decay=args.weight_decay,
    )


def build_finetune_optimizer(model: nn.Module, args: argparse.Namespace) -> torch.optim.Optimizer:
    head_parameter_ids = get_head_parameters(model)
    backbone_params = []
    head_params = []
    for parameter in model.parameters():
        if not parameter.requires_grad:
            continue
        if id(parameter) in head_parameter_ids:
            head_params.append(parameter)
        else:
            backbone_params.append(parameter)

    return torch.optim.AdamW(
        [
            {"params": backbone_params, "lr": args.backbone_lr},
            {"params": head_params, "lr": args.finetune_head_lr},
        ],
        weight_decay=args.weight_decay,
    )


def build_scheduler(
    optimizer: torch.optim.Optimizer,
    stage_epochs: int,
    min_lr: float,
) -> torch.optim.lr_scheduler.LRScheduler:
    return torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer,
        T_max=max(1, stage_epochs),
        eta_min=min_lr,
    )


def compute_confusion_matrix(
    y_true: list[int],
    y_pred: list[int],
    num_classes: int,
) -> list[list[int]]:
    matrix = [[0 for _ in range(num_classes)] for _ in range(num_classes)]
    for target, prediction in zip(y_true, y_pred):
        matrix[target][prediction] += 1
    return matrix


def compute_metrics(
    y_true: list[int],
    y_pred: list[int],
    num_classes: int,
) -> dict[str, Any]:
    matrix = compute_confusion_matrix(y_true, y_pred, num_classes)
    total = sum(sum(row) for row in matrix)
    correct = sum(matrix[index][index] for index in range(num_classes))
    f1_scores = []
    per_class = []

    for index in range(num_classes):
        tp = matrix[index][index]
        fp = sum(matrix[row][index] for row in range(num_classes) if row != index)
        fn = sum(matrix[index][col] for col in range(num_classes) if col != index)
        precision = tp / (tp + fp) if tp + fp > 0 else 0.0
        recall = tp / (tp + fn) if tp + fn > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall > 0 else 0.0
        f1_scores.append(f1)
        per_class.append(
            {
                "label": index,
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "support": sum(matrix[index]),
            }
        )

    return {
        "accuracy": correct / total if total else 0.0,
        "macro_f1": sum(f1_scores) / num_classes,
        "confusion_matrix": matrix,
        "per_class": per_class,
    }


def run_epoch(
    model: nn.Module,
    loader: DataLoader[dict[str, Any]],
    criterion: nn.Module,
    device: torch.device,
    optimizer: torch.optim.Optimizer | None,
    scaler: torch.amp.GradScaler,
    use_amp: bool,
    grad_clip_norm: float,
    num_classes: int,
    classes: list[str] | None = None,
    collect_predictions: bool = False,
) -> dict[str, Any]:
    is_train = optimizer is not None
    model.train(is_train)
    loss_sum = 0.0
    y_true: list[int] = []
    y_pred: list[int] = []
    prediction_rows: list[dict[str, Any]] = []

    for batch in loader:
        images = batch["image"].to(device, non_blocking=True)
        labels = batch["label"].to(device, non_blocking=True)

        if is_train:
            optimizer.zero_grad(set_to_none=True)

        with torch.amp.autocast(device_type=device.type, enabled=use_amp):
            logits = model(images)
            loss = criterion(logits, labels)

        if is_train:
            scaler.scale(loss).backward()
            if grad_clip_norm > 0:
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), grad_clip_norm)
            scaler.step(optimizer)
            scaler.update()

        predictions = logits.argmax(dim=1)
        batch_size = labels.size(0)
        loss_sum += loss.item() * batch_size
        y_true.extend(labels.detach().cpu().tolist())
        y_pred.extend(predictions.detach().cpu().tolist())

        if collect_predictions:
            if classes is None:
                raise ValueError("classes must be provided when collect_predictions=True")
            probabilities = torch.softmax(logits, dim=1).detach().cpu()
            labels_cpu = labels.detach().cpu().tolist()
            predictions_cpu = predictions.detach().cpu().tolist()
            paths = batch["path"]
            for row_index, (path, label, prediction) in enumerate(
                zip(paths, labels_cpu, predictions_cpu)
            ):
                row: dict[str, Any] = {
                    "file_path": path,
                    "actual": classes[label],
                    "predicted": classes[prediction],
                    "correct": int(label == prediction),
                    "confidence": float(probabilities[row_index, prediction]),
                }
                for class_index, class_name in enumerate(classes):
                    row[f"p_{class_name}"] = float(probabilities[row_index, class_index])
                prediction_rows.append(row)

    metrics = compute_metrics(y_true, y_pred, num_classes)
    metrics["loss"] = loss_sum / max(1, len(loader.dataset))
    if collect_predictions:
        metrics["predictions"] = prediction_rows
    return metrics


def save_history(output_dir: Path, history: list[dict[str, Any]]) -> None:
    history_path = output_dir / "history.csv"
    fieldnames = [
        "epoch",
        "stage",
        "lr",
        "train_loss",
        "train_accuracy",
        "train_macro_f1",
        "val_loss",
        "val_accuracy",
        "val_macro_f1",
    ]
    with history_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in history:
            writer.writerow({key: row[key] for key in fieldnames})


def save_confusion_matrix(output_dir: Path, classes: list[str], matrix: list[list[int]]) -> None:
    matrix_path = output_dir / "confusion_matrix.csv"
    with matrix_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["actual\\predicted", *classes])
        for class_name, row in zip(classes, matrix):
            writer.writerow([class_name, *row])


def save_classification_report(
    output_dir: Path,
    classes: list[str],
    per_class: list[dict[str, Any]],
) -> None:
    report_path = output_dir / "classification_report.csv"
    with report_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["class", "precision", "recall", "f1", "support"],
        )
        writer.writeheader()
        for row in per_class:
            writer.writerow(
                {
                    "class": classes[int(row["label"])],
                    "precision": row["precision"],
                    "recall": row["recall"],
                    "f1": row["f1"],
                    "support": row["support"],
                }
            )


def save_predictions(
    output_dir: Path,
    filename: str,
    rows: list[dict[str, Any]],
) -> None:
    if not rows:
        return

    prediction_path = output_dir / filename
    fieldnames = list(rows[0].keys())
    with prediction_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def save_checkpoint(
    output_dir: Path,
    name: str,
    model: nn.Module,
    optimizer: torch.optim.Optimizer,
    classes: list[str],
    epoch: int,
    args: argparse.Namespace,
    metrics: dict[str, Any],
) -> None:
    torch.save(
        {
            "model_state": model.state_dict(),
            "optimizer_state": optimizer.state_dict(),
            "classes": classes,
            "epoch": epoch,
            "args": jsonable_args(args),
            "metrics": metrics,
        },
        output_dir / name,
    )


def current_lr(optimizer: torch.optim.Optimizer) -> float:
    return float(optimizer.param_groups[0]["lr"])


def main() -> int:
    args = parse_args()
    seed_everything(args.seed)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    use_amp = not args.no_amp and device.type == "cuda"
    if device.type == "cuda":
        torch.backends.cudnn.benchmark = True

    train_dataset, val_dataset, classes = build_datasets(args)
    if args.no_balanced_sampler:
        train_sampler = None
        train_shuffle = True
    else:
        train_sampler = build_weighted_sampler(train_dataset, args.important_sample_weight)
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

    model = timm.create_model(
        args.model,
        pretrained=not args.no_pretrained,
        num_classes=len(classes),
    )
    model.to(device)

    criterion = nn.CrossEntropyLoss(label_smoothing=args.label_smoothing)
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)

    config = jsonable_args(args) | {
        "classes": classes,
        "device": str(device),
        "train_samples": len(train_dataset),
        "val_samples": len(val_dataset),
        "amp": use_amp,
    }
    with (args.output_dir / "config.json").open("w", encoding="utf-8") as handle:
        json.dump(config, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    best_val_f1 = -math.inf
    best_val_loss = math.inf
    bad_epochs = 0
    history: list[dict[str, Any]] = []

    optimizer: torch.optim.Optimizer | None = None
    scheduler: torch.optim.lr_scheduler.LRScheduler | None = None
    active_stage = ""

    for epoch in range(1, args.epochs + 1):
        if args.freeze_epochs > 0 and epoch <= args.freeze_epochs:
            stage = "head"
        else:
            stage = "finetune"

        if stage != active_stage:
            active_stage = stage
            if stage == "head":
                set_backbone_trainable(model, trainable=False)
                optimizer = build_head_optimizer(model, args)
                scheduler = build_scheduler(optimizer, args.freeze_epochs, args.min_lr)
            else:
                set_backbone_trainable(model, trainable=True)
                optimizer = build_finetune_optimizer(model, args)
                finetune_epochs = args.epochs - args.freeze_epochs
                scheduler = build_scheduler(optimizer, finetune_epochs, args.min_lr)

        assert optimizer is not None
        assert scheduler is not None
        started = time.time()
        epoch_lr = current_lr(optimizer)

        train_metrics = run_epoch(
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
            val_metrics = run_epoch(
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
            save_checkpoint(
                args.output_dir,
                "best.pt",
                model,
                optimizer,
                classes,
                epoch,
                args,
                val_metrics,
            )
            save_confusion_matrix(
                args.output_dir,
                classes,
                val_metrics["confusion_matrix"],
            )
            save_classification_report(
                args.output_dir,
                classes,
                val_metrics["per_class"],
            )
            save_predictions(
                args.output_dir,
                "val_predictions_best.csv",
                val_metrics["predictions"],
            )
        else:
            bad_epochs += 1

        row = {
            "epoch": epoch,
            "stage": stage,
            "lr": epoch_lr,
            "train_loss": train_metrics["loss"],
            "train_accuracy": train_metrics["accuracy"],
            "train_macro_f1": train_metrics["macro_f1"],
            "val_loss": val_metrics["loss"],
            "val_accuracy": val_metrics["accuracy"],
            "val_macro_f1": val_metrics["macro_f1"],
        }
        history.append(row)
        save_history(args.output_dir, history)
        save_predictions(args.output_dir, "val_predictions_last.csv", val_metrics["predictions"])
        save_checkpoint(args.output_dir, "last.pt", model, optimizer, classes, epoch, args, val_metrics)
        scheduler.step()

        elapsed = time.time() - started
        print(
            f"epoch={epoch:03d} stage={stage} lr={row['lr']:.2e} "
            f"train_loss={row['train_loss']:.4f} train_f1={row['train_macro_f1']:.4f} "
            f"val_loss={row['val_loss']:.4f} val_f1={row['val_macro_f1']:.4f} "
            f"time={elapsed:.1f}s"
        )

        if bad_epochs >= args.early_stop_patience:
            print(f"Early stopping after {bad_epochs} epochs without val macro F1 improvement.")
            break

    print(f"Best val macro F1: {best_val_f1:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
