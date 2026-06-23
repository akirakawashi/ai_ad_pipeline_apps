#!/usr/bin/env python3
"""Prepare CVAT XML annotations and fine-tune the YOLO ad detector."""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import shutil
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import yaml

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "matplotlib"))


IMAGE_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


@dataclass
class PreparedDataset:
    dataset_dir: Path
    data_yaml: Path
    train_txt: Path
    val_txt: Path
    base_train_images: int
    base_val_images: int
    fine_total_images: int
    fine_train_images: int
    fine_val_images: int
    fine_positive_images: int
    fine_background_images: int
    fine_total_boxes: int


@dataclass
class FineRecord:
    image_name: str
    image_member: str
    width: int
    height: int
    boxes: list[tuple[int, float, float, float, float]]
    split: str = ""
    image_path: Path | None = None
    label_path: Path | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fine-tune YOLO detector from a CVAT XML export."
    )
    parser.add_argument(
        "--prepare-only", action="store_true", help="Prepare dataset, do not train."
    )
    parser.add_argument(
        "--cvat-zip", type=Path, default=Path("fine.zip"), help="CVAT export zip."
    )
    parser.add_argument(
        "--base-data-yaml",
        type=Path,
        default=Path("ml/data/detection/yolo/ad_surface_main_v1_80_20/data.yaml"),
        help="Base YOLO dataset YAML to combine with fine-tune data.",
    )
    parser.add_argument(
        "--fine-only",
        action="store_true",
        help="Use only the CVAT fine-tune data, without the base dataset.",
    )
    parser.add_argument(
        "--weights",
        type=Path,
        default=Path("models/detection/best.pt"),
        help="Detector weights to fine-tune from.",
    )
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=Path("ml/data/detection/yolo/ad_surface_fine_v1"),
        help="Prepared combined YOLO dataset directory.",
    )
    parser.add_argument("--overwrite-dataset", action="store_true")
    parser.add_argument("--val-ratio", type=float, default=0.20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--project",
        type=Path,
        default=Path("ml/runs/detection/detect/ad_surface_fine_v1"),
    )
    parser.add_argument("--name", default="yolo11m_img960_fine_v1_ft")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--imgsz", type=int, default=960)
    parser.add_argument("--batch", type=int, default=10)
    parser.add_argument("--lr0", type=float, default=0.0005)
    parser.add_argument("--patience", type=int, default=10)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--device", default=None, help="Torch/Ultralytics device, e.g. cpu or 0."
    )
    parser.add_argument("--exist-ok", action="store_true")
    parser.add_argument("--cache", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[3]
    cvat_zip = resolve_project_path(project_root, args.cvat_zip)
    base_data_yaml = resolve_project_path(project_root, args.base_data_yaml)
    weights = resolve_project_path(project_root, args.weights)
    dataset_dir = resolve_project_path(project_root, args.dataset_dir)
    run_project = resolve_project_path(project_root, args.project)

    if dataset_dir.exists() and not args.overwrite_dataset:
        prepared = load_prepared_dataset(dataset_dir)
        print("using existing prepared dataset")
    else:
        validate_prepare_inputs(
            cvat_zip, base_data_yaml, args.fine_only, args.val_ratio
        )
        prepared = prepare_dataset(
            cvat_zip=cvat_zip,
            base_data_yaml=base_data_yaml,
            dataset_dir=dataset_dir,
            fine_only=args.fine_only,
            val_ratio=args.val_ratio,
            seed=args.seed,
            overwrite=args.overwrite_dataset,
        )
    print_prepared_summary(prepared)

    if args.prepare_only:
        print("prepare_only: training was not started")
        return 0
    if not weights.exists():
        raise FileNotFoundError(weights)

    train_detector(args, prepared.data_yaml, weights, run_project)
    return 0


def resolve_project_path(project_root: Path, value: Path) -> Path:
    return value if value.is_absolute() else project_root / value


def validate_prepare_inputs(
    cvat_zip: Path, base_data_yaml: Path, fine_only: bool, val_ratio: float
) -> None:
    if not cvat_zip.exists():
        raise FileNotFoundError(cvat_zip)
    if not fine_only and not base_data_yaml.exists():
        raise FileNotFoundError(base_data_yaml)
    if not 0.0 < val_ratio < 1.0:
        raise ValueError("--val-ratio must be between 0 and 1")


def load_prepared_dataset(dataset_dir: Path) -> PreparedDataset:
    summary_path = dataset_dir / "dataset_summary.json"
    if not summary_path.exists():
        raise FileNotFoundError(
            f"Prepared dataset exists but summary is missing: {summary_path}. "
            "Use --overwrite-dataset to rebuild it."
        )
    with summary_path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    return PreparedDataset(
        dataset_dir=Path(raw["dataset_dir"]),
        data_yaml=Path(raw["data_yaml"]),
        train_txt=Path(raw["train_txt"]),
        val_txt=Path(raw["val_txt"]),
        base_train_images=int(raw["base_train_images"]),
        base_val_images=int(raw["base_val_images"]),
        fine_total_images=int(raw["fine_total_images"]),
        fine_train_images=int(raw["fine_train_images"]),
        fine_val_images=int(raw["fine_val_images"]),
        fine_positive_images=int(raw["fine_positive_images"]),
        fine_background_images=int(raw["fine_background_images"]),
        fine_total_boxes=int(raw["fine_total_boxes"]),
    )


def prepare_dataset(
    cvat_zip: Path,
    base_data_yaml: Path,
    dataset_dir: Path,
    fine_only: bool,
    val_ratio: float,
    seed: int,
    overwrite: bool,
) -> PreparedDataset:
    if dataset_dir.exists():
        if not overwrite:
            raise FileExistsError(
                f"{dataset_dir} already exists. Use --overwrite-dataset to rebuild it."
            )
        shutil.rmtree(dataset_dir)

    fine_images_train_dir = dataset_dir / "images" / "train"
    fine_images_val_dir = dataset_dir / "images" / "val"
    fine_labels_train_dir = dataset_dir / "labels" / "train"
    fine_labels_val_dir = dataset_dir / "labels" / "val"
    for path in (
        fine_images_train_dir,
        fine_images_val_dir,
        fine_labels_train_dir,
        fine_labels_val_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)

    base_train_images: list[Path] = []
    base_val_images: list[Path] = []
    names: dict[int, str] = {0: "ad_object"}
    if not fine_only:
        base_yaml = load_yaml(base_data_yaml)
        base_root = resolve_base_dataset_root(base_data_yaml, base_yaml)
        base_train_images = collect_split_images(
            base_yaml["train"], base_root, base_data_yaml.parent
        )
        base_val_images = collect_split_images(
            base_yaml["val"], base_root, base_data_yaml.parent
        )
        names = normalize_names(base_yaml.get("names", names))

    with zipfile.ZipFile(cvat_zip) as archive:
        records, archive_names = read_cvat_records(archive)
        if fine_only:
            names = archive_names
        assign_splits(records, val_ratio=val_ratio, seed=seed)
        extract_fine_records(
            archive=archive,
            records=records,
            images_train_dir=fine_images_train_dir,
            images_val_dir=fine_images_val_dir,
            labels_train_dir=fine_labels_train_dir,
            labels_val_dir=fine_labels_val_dir,
        )

    fine_train_images = [
        require_path(record.image_path) for record in records if record.split == "train"
    ]
    fine_val_images = [
        require_path(record.image_path) for record in records if record.split == "val"
    ]
    train_txt = dataset_dir / "train.txt"
    val_txt = dataset_dir / "val.txt"
    data_yaml = dataset_dir / "data.yaml"

    write_lines(train_txt, [*base_train_images, *fine_train_images])
    write_lines(val_txt, [*base_val_images, *fine_val_images])
    write_yaml(
        data_yaml,
        {
            "path": str(dataset_dir.resolve()),
            "train": str(train_txt.resolve()),
            "val": str(val_txt.resolve()),
            "names": names,
        },
    )
    write_manifest(dataset_dir / "fine_manifest.csv", records)

    fine_positive_images = sum(1 for record in records if record.boxes)
    prepared = PreparedDataset(
        dataset_dir=dataset_dir.resolve(),
        data_yaml=data_yaml.resolve(),
        train_txt=train_txt.resolve(),
        val_txt=val_txt.resolve(),
        base_train_images=len(base_train_images),
        base_val_images=len(base_val_images),
        fine_total_images=len(records),
        fine_train_images=len(fine_train_images),
        fine_val_images=len(fine_val_images),
        fine_positive_images=fine_positive_images,
        fine_background_images=len(records) - fine_positive_images,
        fine_total_boxes=sum(len(record.boxes) for record in records),
    )
    write_json(dataset_dir / "dataset_summary.json", asdict(prepared))
    return prepared


def read_cvat_records(
    archive: zipfile.ZipFile,
) -> tuple[list[FineRecord], dict[int, str]]:
    annotations_member = find_member(archive, "annotations.xml")
    if annotations_member is None:
        raise FileNotFoundError("annotations.xml was not found in CVAT zip")

    image_members = {
        Path(member).name: member
        for member in archive.namelist()
        if Path(member).suffix.casefold() in IMAGE_EXTENSIONS and "images/" in member
    }
    root = ET.fromstring(archive.read(annotations_member))
    names = read_label_names(root)
    class_to_id = {label: class_id for class_id, label in names.items()}

    records: list[FineRecord] = []
    for image_el in root.findall("image"):
        image_name = Path(image_el.attrib["name"]).name
        image_member = image_members.get(image_name)
        if image_member is None:
            raise FileNotFoundError(
                f"Image from annotations.xml is missing in zip: {image_name}"
            )
        width = int(float(image_el.attrib["width"]))
        height = int(float(image_el.attrib["height"]))
        boxes: list[tuple[int, float, float, float, float]] = []
        for box_el in image_el.findall("box"):
            label = box_el.attrib["label"]
            class_id = class_to_id[label]
            x1 = clip(float(box_el.attrib["xtl"]), 0.0, float(width))
            y1 = clip(float(box_el.attrib["ytl"]), 0.0, float(height))
            x2 = clip(float(box_el.attrib["xbr"]), 0.0, float(width))
            y2 = clip(float(box_el.attrib["ybr"]), 0.0, float(height))
            if x2 <= x1 or y2 <= y1:
                continue
            boxes.append((class_id, x1, y1, x2, y2))
        records.append(
            FineRecord(
                image_name=image_name,
                image_member=image_member,
                width=width,
                height=height,
                boxes=boxes,
            )
        )

    if not records:
        raise ValueError("No image entries were found in annotations.xml")
    return records, names


def find_member(archive: zipfile.ZipFile, filename: str) -> str | None:
    for member in archive.namelist():
        if Path(member).name == filename:
            return member
    return None


def read_label_names(root: ET.Element) -> dict[int, str]:
    labels: list[str] = []
    for label_el in root.findall(".//labels/label/name"):
        if label_el.text:
            labels.append(label_el.text.strip())
    if not labels:
        labels = ["ad_object"]
    return {index: label for index, label in enumerate(labels)}


def clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def assign_splits(records: list[FineRecord], val_ratio: float, seed: int) -> None:
    shuffled = records[:]
    random.Random(seed).shuffle(shuffled)
    val_count = max(1, int(round(len(shuffled) * val_ratio)))
    val_count = min(val_count, len(shuffled) - 1)
    val_ids = {id(record) for record in shuffled[:val_count]}
    for record in records:
        record.split = "val" if id(record) in val_ids else "train"


def extract_fine_records(
    archive: zipfile.ZipFile,
    records: list[FineRecord],
    images_train_dir: Path,
    images_val_dir: Path,
    labels_train_dir: Path,
    labels_val_dir: Path,
) -> None:
    for record in records:
        images_dir = images_train_dir if record.split == "train" else images_val_dir
        labels_dir = labels_train_dir if record.split == "train" else labels_val_dir
        image_path = images_dir / record.image_name
        label_path = labels_dir / f"{Path(record.image_name).stem}.txt"

        with (
            archive.open(record.image_member) as source,
            image_path.open("wb") as target,
        ):
            shutil.copyfileobj(source, target)
        label_path.write_text(label_text(record), encoding="utf-8")

        record.image_path = image_path.resolve()
        record.label_path = label_path.resolve()


def label_text(record: FineRecord) -> str:
    lines: list[str] = []
    for class_id, x1, y1, x2, y2 in record.boxes:
        x_center = ((x1 + x2) / 2.0) / record.width
        y_center = ((y1 + y2) / 2.0) / record.height
        width = (x2 - x1) / record.width
        height = (y2 - y1) / record.height
        lines.append(
            f"{class_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}"
        )
    return "\n".join(lines) + ("\n" if lines else "")


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected YAML mapping: {path}")
    return data


def normalize_names(names: Any) -> dict[int, str]:
    if isinstance(names, list):
        return {index: str(name) for index, name in enumerate(names)}
    if isinstance(names, dict):
        return {int(index): str(name) for index, name in names.items()}
    return {0: "ad_object"}


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


def require_path(path: Path | None) -> Path:
    if path is None:
        raise ValueError("Expected path to be populated")
    return path


def write_lines(path: Path, lines: list[Path]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for line in lines:
            handle.write(f"{line.resolve()}\n")


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


def write_manifest(path: Path, records: list[FineRecord]) -> None:
    fieldnames = [
        "split",
        "image_name",
        "image_member",
        "image_path",
        "label_path",
        "bbox_count",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "split": record.split,
                    "image_name": record.image_name,
                    "image_member": record.image_member,
                    "image_path": str(record.image_path or ""),
                    "label_path": str(record.label_path or ""),
                    "bbox_count": len(record.boxes),
                }
            )


def print_prepared_summary(prepared: PreparedDataset) -> None:
    print(f"dataset: {prepared.dataset_dir}")
    print(f"data_yaml: {prepared.data_yaml}")
    print(f"base train images: {prepared.base_train_images}")
    print(f"base val images: {prepared.base_val_images}")
    print(f"fine total images: {prepared.fine_total_images}")
    print(f"fine train images: {prepared.fine_train_images}")
    print(f"fine val images: {prepared.fine_val_images}")
    print(f"fine positive images: {prepared.fine_positive_images}")
    print(f"fine background images: {prepared.fine_background_images}")
    print(f"fine total boxes: {prepared.fine_total_boxes}")


def train_detector(
    args: argparse.Namespace, data_yaml: Path, weights: Path, run_project: Path
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
        "cache": args.cache,
    }
    if args.device is not None:
        train_kwargs["device"] = args.device

    model = YOLO(str(weights))
    model.train(**train_kwargs)


if __name__ == "__main__":
    raise SystemExit(main())
