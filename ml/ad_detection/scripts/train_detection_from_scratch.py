#!/usr/bin/env python3
"""Prepare a CVAT YOLO export and train the ad detector from scratch."""

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

import yaml

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "matplotlib"))


IMAGE_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


@dataclass
class PreparedDataset:
    dataset_dir: Path
    data_yaml: Path
    train_txt: Path
    val_txt: Path
    total_images: int
    train_images: int
    val_images: int
    positive_images: int
    background_images: int
    total_boxes: int


@dataclass
class ArchiveRecord:
    image_member: str
    label_member: str
    output_name: str
    split: str = ""
    image_path: Path | None = None
    label_path: Path | None = None
    has_label: bool = False
    bbox_count: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare a CVAT YOLO dataset with 80/20 split and train YOLO from scratch."
    )
    parser.add_argument(
        "--prepare-only", action="store_true", help="Prepare dataset, do not train."
    )
    parser.add_argument(
        "--cvat-zip", type=Path, default=Path("main.zip"), help="CVAT YOLO export zip."
    )
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=Path("ml/data/detection/yolo/ad_surface_main_v1_80_20"),
        help="Prepared YOLO dataset directory.",
    )
    parser.add_argument(
        "--overwrite-dataset",
        action="store_true",
        help="Remove and rebuild --dataset-dir before preparing.",
    )
    parser.add_argument(
        "--val-ratio", type=float, default=0.20, help="Validation split ratio."
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="Deterministic split seed."
    )
    parser.add_argument(
        "--model",
        default="yolo11m.yaml",
        help="YOLO architecture/model. Default yolo11m.yaml trains from random init.",
    )
    parser.add_argument(
        "--project",
        type=Path,
        default=Path("ml/runs/detection/detect/ad_surface_main_v1_from_scratch"),
        help="Ultralytics project directory.",
    )
    parser.add_argument(
        "--name", default="yolo11m_img960_main_v1_scratch", help="Ultralytics run name."
    )
    parser.add_argument("--epochs", type=int, default=150)
    parser.add_argument("--imgsz", type=int, default=960)
    parser.add_argument("--batch", type=int, default=10)
    parser.add_argument("--patience", type=int, default=30)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--device", default=None, help="Torch/Ultralytics device, e.g. cpu or 0."
    )
    parser.add_argument(
        "--exist-ok",
        action="store_true",
        help="Allow Ultralytics to reuse run directory.",
    )
    parser.add_argument(
        "--cache", action="store_true", help="Enable Ultralytics dataset caching."
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[3]
    cvat_zip = resolve_project_path(project_root, args.cvat_zip)
    dataset_dir = resolve_project_path(project_root, args.dataset_dir)
    run_project = resolve_project_path(project_root, args.project)

    if dataset_dir.exists() and not args.overwrite_dataset:
        prepared = load_prepared_dataset(dataset_dir)
        print("using existing prepared dataset")
    else:
        validate_prepare_args(cvat_zip, args.val_ratio)
        prepared = prepare_dataset_from_cvat_zip(
            cvat_zip=cvat_zip,
            dataset_dir=dataset_dir,
            val_ratio=args.val_ratio,
            seed=args.seed,
            overwrite=args.overwrite_dataset,
        )
    print_prepared_summary(prepared)

    if args.prepare_only:
        print("prepare_only: training was not started")
        return 0

    train_detector(args, prepared.data_yaml, run_project)
    return 0


def resolve_project_path(project_root: Path, value: Path) -> Path:
    return value if value.is_absolute() else project_root / value


def validate_prepare_args(cvat_zip: Path, val_ratio: float) -> None:
    if not cvat_zip.exists():
        raise FileNotFoundError(cvat_zip)
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
        total_images=int(raw["total_images"]),
        train_images=int(raw["train_images"]),
        val_images=int(raw["val_images"]),
        positive_images=int(raw["positive_images"]),
        background_images=int(raw["background_images"]),
        total_boxes=int(raw["total_boxes"]),
    )


def prepare_dataset_from_cvat_zip(
    cvat_zip: Path,
    dataset_dir: Path,
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

    images_train_dir = dataset_dir / "images" / "train"
    images_val_dir = dataset_dir / "images" / "val"
    labels_train_dir = dataset_dir / "labels" / "train"
    labels_val_dir = dataset_dir / "labels" / "val"
    for path in (images_train_dir, images_val_dir, labels_train_dir, labels_val_dir):
        path.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(cvat_zip) as archive:
        names = read_archive_names(archive)
        records = collect_archive_records(archive)
        assign_splits(records, val_ratio=val_ratio, seed=seed)
        extract_records(
            archive=archive,
            records=records,
            images_train_dir=images_train_dir,
            images_val_dir=images_val_dir,
            labels_train_dir=labels_train_dir,
            labels_val_dir=labels_val_dir,
        )

    train_records = [record for record in records if record.split == "train"]
    val_records = [record for record in records if record.split == "val"]
    train_txt = dataset_dir / "train.txt"
    val_txt = dataset_dir / "val.txt"
    data_yaml = dataset_dir / "data.yaml"

    write_lines(
        train_txt, [require_path(record.image_path) for record in train_records]
    )
    write_lines(val_txt, [require_path(record.image_path) for record in val_records])
    write_yaml(
        data_yaml,
        {
            "path": str(dataset_dir.resolve()),
            "train": str(train_txt.resolve()),
            "val": str(val_txt.resolve()),
            "names": names,
        },
    )
    write_manifest(dataset_dir / "manifest.csv", records)

    positive_images = sum(1 for record in records if record.has_label)
    total_boxes = sum(record.bbox_count for record in records)
    prepared = PreparedDataset(
        dataset_dir=dataset_dir.resolve(),
        data_yaml=data_yaml.resolve(),
        train_txt=train_txt.resolve(),
        val_txt=val_txt.resolve(),
        total_images=len(records),
        train_images=len(train_records),
        val_images=len(val_records),
        positive_images=positive_images,
        background_images=len(records) - positive_images,
        total_boxes=total_boxes,
    )
    write_json(dataset_dir / "dataset_summary.json", asdict(prepared))
    return prepared


def read_archive_names(archive: zipfile.ZipFile) -> dict[int, str]:
    data_yaml_member = find_archive_member(archive, "data.yaml")
    if data_yaml_member is None:
        return {0: "ad_object"}
    with archive.open(data_yaml_member) as handle:
        data = yaml.safe_load(handle.read().decode("utf-8")) or {}
    names = data.get("names", {0: "ad_object"})
    if isinstance(names, list):
        return {index: str(name) for index, name in enumerate(names)}
    return {int(index): str(name) for index, name in names.items()}


def find_archive_member(archive: zipfile.ZipFile, name: str) -> str | None:
    for member in archive.namelist():
        if Path(member).name == name:
            return member
    return None


def collect_archive_records(archive: zipfile.ZipFile) -> list[ArchiveRecord]:
    members = archive.namelist()
    image_members = sorted(member for member in members if is_image_member(member))
    label_members = {
        Path(member).stem: member for member in members if is_label_member(member)
    }
    if not image_members:
        raise ValueError("No images were found in CVAT export")

    used_names: set[str] = set()
    records: list[ArchiveRecord] = []
    for image_member in image_members:
        output_name = unique_output_name(Path(image_member).name, used_names)
        label_member = label_members.get(Path(image_member).stem, "")
        records.append(
            ArchiveRecord(
                image_member=image_member,
                label_member=label_member,
                output_name=output_name,
            )
        )
    return records


def is_image_member(member: str) -> bool:
    path = Path(member)
    return path.suffix.casefold() in IMAGE_EXTENSIONS and "images/" in member


def is_label_member(member: str) -> bool:
    path = Path(member)
    return path.suffix == ".txt" and "labels/" in member


def unique_output_name(filename: str, used_names: set[str]) -> str:
    candidate = filename
    if candidate not in used_names:
        used_names.add(candidate)
        return candidate

    path = Path(filename)
    index = 1
    while True:
        candidate = f"{path.stem}_dup{index:03d}{path.suffix}"
        if candidate not in used_names:
            used_names.add(candidate)
            return candidate
        index += 1


def assign_splits(records: list[ArchiveRecord], val_ratio: float, seed: int) -> None:
    shuffled = records[:]
    random.Random(seed).shuffle(shuffled)
    val_count = max(1, int(round(len(shuffled) * val_ratio)))
    val_count = min(val_count, len(shuffled) - 1)
    val_ids = {id(record) for record in shuffled[:val_count]}
    for record in records:
        record.split = "val" if id(record) in val_ids else "train"


def extract_records(
    archive: zipfile.ZipFile,
    records: list[ArchiveRecord],
    images_train_dir: Path,
    images_val_dir: Path,
    labels_train_dir: Path,
    labels_val_dir: Path,
) -> None:
    for record in records:
        images_dir = images_train_dir if record.split == "train" else images_val_dir
        labels_dir = labels_train_dir if record.split == "train" else labels_val_dir
        image_path = images_dir / record.output_name
        label_path = labels_dir / f"{Path(record.output_name).stem}.txt"

        with (
            archive.open(record.image_member) as source,
            image_path.open("wb") as target,
        ):
            shutil.copyfileobj(source, target)

        if record.label_member:
            label_text = archive.read(record.label_member).decode("utf-8").strip()
            label_path.write_text(
                label_text + ("\n" if label_text else ""), encoding="utf-8"
            )
        else:
            label_text = ""
            label_path.write_text("", encoding="utf-8")

        record.image_path = image_path.resolve()
        record.label_path = label_path.resolve()
        record.bbox_count = count_label_boxes(label_text)
        record.has_label = record.bbox_count > 0


def count_label_boxes(label_text: str) -> int:
    return sum(1 for line in label_text.splitlines() if line.strip())


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


def write_manifest(path: Path, records: list[ArchiveRecord]) -> None:
    fieldnames = [
        "split",
        "image_member",
        "label_member",
        "output_name",
        "image_path",
        "label_path",
        "has_label",
        "bbox_count",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "split": record.split,
                    "image_member": record.image_member,
                    "label_member": record.label_member,
                    "output_name": record.output_name,
                    "image_path": str(record.image_path or ""),
                    "label_path": str(record.label_path or ""),
                    "has_label": int(record.has_label),
                    "bbox_count": record.bbox_count,
                }
            )


def print_prepared_summary(prepared: PreparedDataset) -> None:
    print(f"dataset: {prepared.dataset_dir}")
    print(f"data_yaml: {prepared.data_yaml}")
    print(f"total images: {prepared.total_images}")
    print(f"train images: {prepared.train_images}")
    print(f"val images: {prepared.val_images}")
    print(f"positive images: {prepared.positive_images}")
    print(f"background images: {prepared.background_images}")
    print(f"total boxes: {prepared.total_boxes}")


def train_detector(
    args: argparse.Namespace, data_yaml: Path, run_project: Path
) -> None:
    from ultralytics import YOLO

    train_kwargs: dict[str, Any] = {
        "data": str(data_yaml),
        "epochs": args.epochs,
        "imgsz": args.imgsz,
        "batch": args.batch,
        "patience": args.patience,
        "workers": args.workers,
        "project": str(run_project),
        "name": args.name,
        "exist_ok": args.exist_ok,
        "plots": True,
        "cache": args.cache,
        "pretrained": False,
    }
    if args.device is not None:
        train_kwargs["device"] = args.device

    model = YOLO(args.model)
    model.train(**train_kwargs)


if __name__ == "__main__":
    raise SystemExit(main())
