#!/usr/bin/env python3
"""Continue YOLO detector fine-tuning with hard-negative CVAT export."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "matplotlib"))


IMAGE_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


@dataclass
class PreparedDataset:
    dataset_dir: Path
    data_yaml: Path
    train_txt: Path
    val_txt: Path
    base_train_count: int
    base_val_count: int
    hard_negative_count: int
    hard_negative_positive_count: int
    hard_negative_background_count: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare hard-negative dataset and continue fine-tuning the YOLO detector."
    )
    parser.add_argument(
        "--prepare-only", action="store_true", help="Prepare dataset, do not train."
    )
    parser.add_argument(
        "--hard-negative-zip",
        type=Path,
        default=Path("1.zip"),
        help="CVAT YOLO export zip with hard-negative frames.",
    )
    parser.add_argument(
        "--base-data-yaml",
        type=Path,
        default=Path(
            "ml/data/detection/yolo/ad_surface_full_v1_finetune_cvat_corrections/data.yaml"
        ),
        help="Existing YOLO dataset YAML. Its validation split is reused unchanged.",
    )
    parser.add_argument(
        "--weights",
        type=Path,
        default=Path(
            "ml/runs/detection/detect/ad_surface_full_v1_finetune_cvat_corrections/"
            "yolo11m_img960_antifp_cvat_corrections_ft_v1/weights/best.pt"
        ),
        help="Weights to continue fine-tuning from.",
    )
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=Path("ml/data/detection/yolo/ad_surface_full_v1_hard_negatives_v1"),
        help="Prepared combined YOLO dataset directory.",
    )
    parser.add_argument(
        "--overwrite-dataset",
        action="store_true",
        help="Remove and rebuild --dataset-dir before preparing.",
    )
    parser.add_argument(
        "--project",
        type=Path,
        default=Path("ml/runs/detection/detect/ad_surface_full_v1_hard_negatives_v1"),
        help="Ultralytics project directory for the new run.",
    )
    parser.add_argument(
        "--name",
        default="yolo11m_img960_antifp_hard_negatives_v1",
        help="Ultralytics run name.",
    )
    parser.add_argument("--epochs", type=int, default=15)
    parser.add_argument("--imgsz", type=int, default=960)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--lr0", type=float, default=0.001)
    parser.add_argument("--patience", type=int, default=5)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--device", default=None, help="Torch/Ultralytics device, e.g. cpu or 0."
    )
    parser.add_argument(
        "--freeze",
        type=int,
        default=0,
        help="Freeze first N layers. Default: no freeze.",
    )
    parser.add_argument(
        "--exist-ok",
        action="store_true",
        help="Allow Ultralytics to reuse run directory.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[3]
    hard_negative_zip = resolve_project_path(project_root, args.hard_negative_zip)
    base_data_yaml = resolve_project_path(project_root, args.base_data_yaml)
    weights = resolve_project_path(project_root, args.weights)
    dataset_dir = resolve_project_path(project_root, args.dataset_dir)
    run_project = resolve_project_path(project_root, args.project)

    validate_training_inputs(weights, args.prepare_only)
    if dataset_dir.exists() and not args.overwrite_dataset:
        prepared = load_prepared_dataset(dataset_dir)
        print("using existing prepared dataset")
    else:
        validate_prepare_inputs(hard_negative_zip, base_data_yaml)
        prepared = prepare_dataset(
            hard_negative_zip=hard_negative_zip,
            base_data_yaml=base_data_yaml,
            dataset_dir=dataset_dir,
            overwrite=args.overwrite_dataset,
        )
    print_prepared_summary(prepared)

    if args.prepare_only:
        print("prepare_only: training was not started")
        return 0

    train_detector(args, prepared.data_yaml, weights, run_project)
    return 0


def resolve_project_path(project_root: Path, value: Path) -> Path:
    return value if value.is_absolute() else project_root / value


def validate_training_inputs(weights: Path, prepare_only: bool) -> None:
    if not prepare_only and not weights.exists():
        raise FileNotFoundError(weights)


def validate_prepare_inputs(hard_negative_zip: Path, base_data_yaml: Path) -> None:
    if not hard_negative_zip.exists():
        raise FileNotFoundError(
            f"{hard_negative_zip} is required only when preparing/rebuilding the dataset. "
            "Use the existing prepared dataset or restore the zip."
        )
    if not base_data_yaml.exists():
        raise FileNotFoundError(base_data_yaml)


def load_prepared_dataset(dataset_dir: Path) -> PreparedDataset:
    data_yaml = dataset_dir / "data.yaml"
    train_txt = dataset_dir / "train.txt"
    val_txt = dataset_dir / "val.txt"
    summary_path = dataset_dir / "dataset_summary.json"
    for path in (data_yaml, train_txt, val_txt):
        if not path.exists():
            raise FileNotFoundError(f"Prepared dataset is incomplete: {path}")

    if summary_path.exists():
        with summary_path.open("r", encoding="utf-8") as handle:
            summary = json.load(handle)
        return PreparedDataset(
            dataset_dir=Path(summary.get("dataset_dir", dataset_dir)),
            data_yaml=Path(summary.get("data_yaml", data_yaml)),
            train_txt=Path(summary.get("train_txt", train_txt)),
            val_txt=Path(summary.get("val_txt", val_txt)),
            base_train_count=int(summary.get("base_train_count", 0)),
            base_val_count=int(summary.get("base_val_count", 0)),
            hard_negative_count=int(summary.get("hard_negative_count", 0)),
            hard_negative_positive_count=int(
                summary.get("hard_negative_positive_count", 0)
            ),
            hard_negative_background_count=int(
                summary.get("hard_negative_background_count", 0)
            ),
        )

    hard_images_count = count_files(dataset_dir / "images" / "train")
    hard_positive_count = count_non_empty_files(dataset_dir / "labels" / "train")
    train_count = count_lines(train_txt)
    val_count = count_lines(val_txt)
    return PreparedDataset(
        dataset_dir=dataset_dir,
        data_yaml=data_yaml,
        train_txt=train_txt,
        val_txt=val_txt,
        base_train_count=max(0, train_count - hard_images_count),
        base_val_count=val_count,
        hard_negative_count=hard_images_count,
        hard_negative_positive_count=hard_positive_count,
        hard_negative_background_count=max(0, hard_images_count - hard_positive_count),
    )


def count_files(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for item in path.iterdir() if item.is_file())


def count_non_empty_files(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(
        1 for item in path.iterdir() if item.is_file() and item.stat().st_size > 0
    )


def count_lines(path: Path) -> int:
    return sum(
        1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    )


def prepare_dataset(
    hard_negative_zip: Path,
    base_data_yaml: Path,
    dataset_dir: Path,
    overwrite: bool,
) -> PreparedDataset:
    if dataset_dir.exists():
        if not overwrite:
            raise FileExistsError(
                f"{dataset_dir} already exists. Use --overwrite-dataset to rebuild it."
            )
        shutil.rmtree(dataset_dir)

    dataset_dir.mkdir(parents=True, exist_ok=True)
    hard_images_dir = dataset_dir / "images" / "train"
    hard_labels_dir = dataset_dir / "labels" / "train"
    hard_images_dir.mkdir(parents=True, exist_ok=True)
    hard_labels_dir.mkdir(parents=True, exist_ok=True)

    base_yaml = load_yaml(base_data_yaml)
    base_root = resolve_base_dataset_root(base_data_yaml, base_yaml)
    names = base_yaml.get("names", {0: "ad_object"})

    base_train_images = collect_split_images(
        base_yaml["train"], base_root, base_data_yaml.parent
    )
    base_val_images = collect_split_images(
        base_yaml["val"], base_root, base_data_yaml.parent
    )
    hard_manifest = extract_hard_negative_zip(
        hard_negative_zip, hard_images_dir, hard_labels_dir
    )
    hard_images = [row["image_path"] for row in hard_manifest]

    train_txt = dataset_dir / "train.txt"
    val_txt = dataset_dir / "val.txt"
    data_yaml = dataset_dir / "data.yaml"
    write_lines(train_txt, [*base_train_images, *hard_images])
    write_lines(val_txt, base_val_images)
    write_yaml(
        data_yaml,
        {
            "path": str(dataset_dir),
            "train": str(train_txt),
            "val": str(val_txt),
            "names": names,
        },
    )
    write_hard_negative_manifest(
        dataset_dir / "hard_negative_manifest.csv", hard_manifest
    )

    hard_positive_count = sum(1 for row in hard_manifest if row["has_label"])
    prepared = PreparedDataset(
        dataset_dir=dataset_dir,
        data_yaml=data_yaml,
        train_txt=train_txt,
        val_txt=val_txt,
        base_train_count=len(base_train_images),
        base_val_count=len(base_val_images),
        hard_negative_count=len(hard_images),
        hard_negative_positive_count=hard_positive_count,
        hard_negative_background_count=len(hard_images) - hard_positive_count,
    )
    write_json(dataset_dir / "dataset_summary.json", asdict(prepared))
    return prepared


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected YAML mapping: {path}")
    return data


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=True)


def write_json(path: Path, data: dict[str, Any]) -> None:
    serializable = {
        key: str(value) if isinstance(value, Path) else value
        for key, value in data.items()
    }
    with path.open("w", encoding="utf-8") as handle:
        json.dump(serializable, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def resolve_base_dataset_root(base_data_yaml: Path, base_yaml: dict[str, Any]) -> Path:
    yaml_path = base_yaml.get("path")
    if yaml_path:
        candidate = Path(yaml_path)
        if not candidate.is_absolute():
            candidate = base_data_yaml.parent / candidate
        if candidate.exists():
            return candidate
    return base_data_yaml.parent


def collect_split_images(
    split_value: str | list[str], dataset_root: Path, yaml_dir: Path
) -> list[Path]:
    values = split_value if isinstance(split_value, list) else [split_value]
    images: list[Path] = []
    for value in values:
        path = Path(value)
        if not path.is_absolute():
            root_candidate = dataset_root / path
            yaml_candidate = yaml_dir / path
            path = root_candidate if root_candidate.exists() else yaml_candidate
        if path.suffix == ".txt":
            images.extend(read_image_list(path, dataset_root))
        elif path.is_dir():
            images.extend(
                sorted(
                    p.resolve()
                    for p in path.rglob("*")
                    if p.suffix.casefold() in IMAGE_EXTENSIONS
                )
            )
        elif path.is_file() and path.suffix.casefold() in IMAGE_EXTENSIONS:
            images.append(path.resolve())
        else:
            raise FileNotFoundError(f"Could not resolve dataset split: {value}")
    return unique_paths(images)


def read_image_list(path: Path, dataset_root: Path) -> list[Path]:
    images: list[Path] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        image_path = Path(line)
        if not image_path.is_absolute():
            image_path = dataset_root / image_path
        images.append(image_path.resolve())
    return images


def unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return unique


def extract_hard_negative_zip(
    hard_negative_zip: Path,
    images_dir: Path,
    labels_dir: Path,
) -> list[dict[str, Any]]:
    with zipfile.ZipFile(hard_negative_zip) as archive:
        image_members = sorted(
            member for member in archive.namelist() if is_zip_image(member)
        )
        label_members = {
            Path(member).stem: member
            for member in archive.namelist()
            if member.startswith(("labels/train/", "data/labels/train/"))
            and member.endswith(".txt")
        }

        manifest: list[dict[str, Any]] = []
        for image_member in image_members:
            image_name = Path(image_member).name
            label_name = f"{Path(image_name).stem}.txt"
            image_path = images_dir / image_name
            label_path = labels_dir / label_name

            with archive.open(image_member) as source, image_path.open("wb") as target:
                shutil.copyfileobj(source, target)

            label_member = label_members.get(Path(image_name).stem)
            if label_member:
                with (
                    archive.open(label_member) as source,
                    label_path.open("wb") as target,
                ):
                    shutil.copyfileobj(source, target)
                has_label = label_path.stat().st_size > 0
            else:
                label_path.write_text("", encoding="utf-8")
                has_label = False

            manifest.append(
                {
                    "image_path": image_path.resolve(),
                    "label_path": label_path.resolve(),
                    "image_member": image_member,
                    "label_member": label_member or "",
                    "has_label": has_label,
                }
            )
    return manifest


def is_zip_image(member: str) -> bool:
    path = Path(member)
    return path.suffix.casefold() in IMAGE_EXTENSIONS and any(
        member.startswith(prefix) for prefix in ("images/train/", "data/images/train/")
    )


def write_lines(path: Path, lines: list[Path]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for line in lines:
            handle.write(f"{line.resolve()}\n")


def write_hard_negative_manifest(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "image_path",
        "label_path",
        "image_member",
        "label_member",
        "has_label",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] for key in fieldnames})


def print_prepared_summary(prepared: PreparedDataset) -> None:
    print(f"dataset: {prepared.dataset_dir}")
    print(f"data_yaml: {prepared.data_yaml}")
    print(f"base train images: {prepared.base_train_count}")
    print(f"base val images: {prepared.base_val_count} (reused unchanged)")
    print(f"hard-negative images: {prepared.hard_negative_count}")
    print(f"hard-negative with labels: {prepared.hard_negative_positive_count}")
    print(f"hard-negative background only: {prepared.hard_negative_background_count}")


def train_detector(
    args: argparse.Namespace,
    data_yaml: Path,
    weights: Path,
    run_project: Path,
) -> None:
    from ultralytics import YOLO

    train_kwargs: dict[str, Any] = {
        "data": str(data_yaml),
        "epochs": args.epochs,
        "imgsz": args.imgsz,
        "batch": args.batch,
        "lr0": args.lr0,
        "patience": args.patience,
        "workers": args.workers,
        "project": str(run_project),
        "name": args.name,
        "exist_ok": args.exist_ok,
        "plots": True,
        "cache": False,
    }
    if args.device is not None:
        train_kwargs["device"] = args.device
    if args.freeze > 0:
        train_kwargs["freeze"] = args.freeze

    model = YOLO(str(weights))
    model.train(**train_kwargs)


if __name__ == "__main__":
    raise SystemExit(main())
