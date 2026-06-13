#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import random
import shutil
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_DATASET_DIR = PROJECT_ROOT / "data/yolo/ad_surface_v2"
CURATED_DATASET_DIR = PROJECT_ROOT / "data/cvat_exports/video_predict_curated_checked"
OUTPUT_DATASET_DIR = PROJECT_ROOT / "data/yolo/ad_surface_v3_finetune"
IMAGE_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".webp"}
CLASS_NAMES = {0: "ad_object"}


@dataclass(frozen=True)
class DatasetItem:
    image_path: Path
    label_path: Path
    source_dataset: str
    source_split: str
    output_split: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a YOLO fine-tuning dataset from ad_surface_v2 and checked "
            "video hard examples exported from CVAT."
        )
    )
    parser.add_argument("--base", type=Path, default=BASE_DATASET_DIR)
    parser.add_argument("--curated", type=Path, default=CURATED_DATASET_DIR)
    parser.add_argument("--output", type=Path, default=OUTPUT_DATASET_DIR)
    parser.add_argument("--new-val-fraction", type=float, default=0.20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def list_images(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(
        path for path in directory.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def count_boxes(label_path: Path) -> int:
    if not label_path.exists():
        return 0
    return sum(1 for line in label_path.read_text(encoding="utf-8").splitlines() if line.strip())


def validate_yolo_label(label_path: Path) -> None:
    if not label_path.exists():
        return

    for line_number, line in enumerate(label_path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue

        parts = stripped.split()
        if len(parts) != 5:
            raise ValueError(f"{label_path}:{line_number}: expected 5 YOLO fields, got {len(parts)}")

        try:
            class_id = int(parts[0])
            x_center, y_center, width, height = (float(value) for value in parts[1:])
        except ValueError as exc:
            raise ValueError(f"{label_path}:{line_number}: invalid YOLO numeric value") from exc

        if class_id not in CLASS_NAMES:
            raise ValueError(f"{label_path}:{line_number}: unknown class id {class_id}")

        values = (x_center, y_center, width, height)
        if any(value < 0.0 or value > 1.0 for value in values):
            raise ValueError(f"{label_path}:{line_number}: coordinates must be normalized to 0..1")

        if width <= 0.0 or height <= 0.0:
            raise ValueError(f"{label_path}:{line_number}: width and height must be positive")


def split_curated_items(
    curated_dir: Path,
    val_fraction: float,
    seed: int,
) -> list[DatasetItem]:
    image_dir = curated_dir / "images/train"
    label_dir = curated_dir / "labels/train"
    images = list_images(image_dir)
    if not images:
        raise FileNotFoundError(f"No images found in {image_dir}")

    positive: list[Path] = []
    negative: list[Path] = []
    for image_path in images:
        label_path = label_dir / f"{image_path.stem}.txt"
        validate_yolo_label(label_path)
        if count_boxes(label_path) > 0:
            positive.append(image_path)
        else:
            negative.append(image_path)

    rng = random.Random(seed)

    def choose_val(items: list[Path]) -> set[Path]:
        shuffled = items[:]
        rng.shuffle(shuffled)
        if len(shuffled) <= 1:
            return set()
        val_count = max(1, round(len(shuffled) * val_fraction))
        val_count = min(val_count, len(shuffled) - 1)
        return set(shuffled[:val_count])

    val_images = choose_val(positive) | choose_val(negative)
    items: list[DatasetItem] = []
    for image_path in images:
        split = "val" if image_path in val_images else "train"
        items.append(
            DatasetItem(
                image_path=image_path,
                label_path=label_dir / f"{image_path.stem}.txt",
                source_dataset="video_predict_curated_checked",
                source_split="train",
                output_split=split,
            )
        )
    return items


def base_items(base_dir: Path) -> list[DatasetItem]:
    items: list[DatasetItem] = []
    for split in ("train", "val"):
        image_dir = base_dir / f"images/{split}"
        label_dir = base_dir / f"labels/{split}"
        for image_path in list_images(image_dir):
            label_path = label_dir / f"{image_path.stem}.txt"
            validate_yolo_label(label_path)
            items.append(
                DatasetItem(
                    image_path=image_path,
                    label_path=label_path,
                    source_dataset="ad_surface_v2",
                    source_split=split,
                    output_split=split,
                )
            )
    if not items:
        raise FileNotFoundError(f"No base dataset images found in {base_dir}")
    return items


def prepare_output(output_dir: Path, overwrite: bool) -> None:
    if output_dir.exists():
        if not overwrite:
            raise FileExistsError(f"{output_dir} already exists. Re-run with --overwrite to rebuild it.")
        shutil.rmtree(output_dir)

    for split in ("train", "val"):
        (output_dir / f"images/{split}").mkdir(parents=True, exist_ok=True)
        (output_dir / f"labels/{split}").mkdir(parents=True, exist_ok=True)


def relative_to_project(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def copy_item(item: DatasetItem, output_dir: Path) -> dict[str, str | int]:
    image_output = output_dir / f"images/{item.output_split}" / item.image_path.name
    label_output = output_dir / f"labels/{item.output_split}" / f"{item.image_path.stem}.txt"

    if image_output.exists():
        raise FileExistsError(f"Duplicate output image path: {image_output}")

    shutil.copy2(item.image_path, image_output)
    if item.label_path.exists():
        shutil.copy2(item.label_path, label_output)
    else:
        label_output.write_text("", encoding="utf-8")

    box_count = count_boxes(label_output)
    return {
        "split": item.output_split,
        "image": relative_to_project(image_output),
        "label": relative_to_project(label_output),
        "source_dataset": item.source_dataset,
        "source_split": item.source_split,
        "source_image": relative_to_project(item.image_path),
        "source_label": relative_to_project(item.label_path),
        "box_count": box_count,
        "has_objects": int(box_count > 0),
    }


def write_data_yaml(output_dir: Path) -> None:
    names_yaml = "\n".join(f"  {class_id}: {name}" for class_id, name in CLASS_NAMES.items())
    content = (
        f"path: {output_dir}\n"
        "train: images/train\n"
        "val: images/val\n"
        "names:\n"
        f"{names_yaml}\n"
    )
    (output_dir / "data.yaml").write_text(content, encoding="utf-8")


def write_split_files(output_dir: Path, rows: list[dict[str, str | int]]) -> None:
    for split in ("train", "val"):
        image_paths = [
            str(Path(row["image"]).relative_to(relative_to_project(output_dir)))
            if str(row["image"]).startswith(relative_to_project(output_dir))
            else str(Path(row["image"]))
            for row in rows
            if row["split"] == split
        ]
        (output_dir / f"{split}.txt").write_text("\n".join(image_paths) + "\n", encoding="utf-8")

    with (output_dir / "split_manifest.csv").open("w", newline="", encoding="utf-8") as file:
        fieldnames = [
            "split",
            "image",
            "label",
            "source_dataset",
            "source_split",
            "source_image",
            "source_label",
            "box_count",
            "has_objects",
        ]
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def print_summary(rows: list[dict[str, str | int]], output_dir: Path) -> None:
    print(f"Dataset written to: {output_dir}")
    for split in ("train", "val"):
        split_rows = [row for row in rows if row["split"] == split]
        boxes = sum(int(row["box_count"]) for row in split_rows)
        positives = sum(int(row["has_objects"]) for row in split_rows)
        negatives = len(split_rows) - positives
        print(
            f"{split}: images={len(split_rows)}, boxes={boxes}, "
            f"positive_images={positives}, negative_images={negatives}"
        )


def main() -> None:
    args = parse_args()
    base_dir = args.base.resolve()
    curated_dir = args.curated.resolve()
    output_dir = args.output.resolve()

    if not base_dir.exists():
        raise FileNotFoundError(base_dir)
    if not curated_dir.exists():
        raise FileNotFoundError(curated_dir)
    if not 0.0 < args.new_val_fraction < 1.0:
        raise ValueError("--new-val-fraction must be between 0 and 1")

    items = base_items(base_dir)
    items.extend(split_curated_items(curated_dir, args.new_val_fraction, args.seed))

    prepare_output(output_dir, args.overwrite)
    rows = [copy_item(item, output_dir) for item in items]
    write_data_yaml(output_dir)
    write_split_files(output_dir, rows)
    print_summary(rows, output_dir)


if __name__ == "__main__":
    main()
