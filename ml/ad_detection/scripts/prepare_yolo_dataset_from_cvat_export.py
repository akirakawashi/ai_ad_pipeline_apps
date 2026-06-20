#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import random
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ARCHIVE = PROJECT_ROOT / "detect_new.zip"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "ml/data/detection/yolo/ad_surface_full_v1"
IMAGE_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


@dataclass(frozen=True)
class ExportItem:
    image_member: str
    label_member: str | None
    stem: str
    suffix: str
    box_count: int

    @property
    def has_objects(self) -> bool:
        return self.box_count > 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a clean YOLO train/val dataset from a CVAT Ultralytics YOLO "
            "Detection export. Missing label files are treated as empty labels."
        )
    )
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--val-fraction", type=float, default=0.20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def read_names(archive: zipfile.ZipFile) -> dict[int, str]:
    if "data.yaml" not in archive.namelist():
        return {0: "ad_object"}

    data = yaml.safe_load(archive.read("data.yaml").decode("utf-8")) or {}
    names = data.get("names") or {0: "ad_object"}
    if isinstance(names, list):
        return {idx: str(name) for idx, name in enumerate(names)}
    return {int(class_id): str(name) for class_id, name in names.items()}


def list_items(archive: zipfile.ZipFile) -> list[ExportItem]:
    members = archive.namelist()
    image_members = sorted(
        member
        for member in members
        if member.startswith("images/")
        and not member.endswith("/")
        and Path(member).suffix.lower() in IMAGE_EXTENSIONS
    )
    label_members = {
        Path(member).stem: member
        for member in members
        if member.startswith("labels/") and member.lower().endswith(".txt")
    }

    if not image_members:
        raise ValueError("No images found under images/ in CVAT export.")

    items: list[ExportItem] = []
    for image_member in image_members:
        image_path = Path(image_member)
        label_member = label_members.get(image_path.stem)
        box_count = 0
        if label_member is not None:
            label_text = archive.read(label_member).decode("utf-8").strip()
            box_count = sum(1 for line in label_text.splitlines() if line.strip())

        items.append(
            ExportItem(
                image_member=image_member,
                label_member=label_member,
                stem=image_path.stem,
                suffix=image_path.suffix.lower(),
                box_count=box_count,
            )
        )
    return items


def validate_label_text(label_text: str, label_member: str, class_names: dict[int, str]) -> None:
    for line_number, line in enumerate(label_text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue

        parts = stripped.split()
        if len(parts) != 5:
            raise ValueError(f"{label_member}:{line_number}: expected 5 YOLO fields, got {len(parts)}")

        try:
            class_id = int(parts[0])
            x_center, y_center, width, height = (float(value) for value in parts[1:])
        except ValueError as exc:
            raise ValueError(f"{label_member}:{line_number}: invalid numeric value") from exc

        if class_id not in class_names:
            raise ValueError(f"{label_member}:{line_number}: unknown class id {class_id}")

        values = (x_center, y_center, width, height)
        if any(value < 0.0 or value > 1.0 for value in values):
            raise ValueError(f"{label_member}:{line_number}: coordinates must be normalized to 0..1")

        if width <= 0.0 or height <= 0.0:
            raise ValueError(f"{label_member}:{line_number}: width and height must be positive")


def stratified_split(
    items: list[ExportItem],
    val_fraction: float,
    seed: int,
) -> dict[str, str]:
    rng = random.Random(seed)
    split_by_image: dict[str, str] = {}

    for has_objects in (True, False):
        group = [item for item in items if item.has_objects == has_objects]
        rng.shuffle(group)

        if len(group) <= 1:
            val_count = 0
        else:
            val_count = round(len(group) * val_fraction)
            val_count = max(1, min(val_count, len(group) - 1))

        for item in group[:val_count]:
            split_by_image[item.image_member] = "val"
        for item in group[val_count:]:
            split_by_image[item.image_member] = "train"

    return split_by_image


def prepare_output(output_dir: Path, overwrite: bool) -> None:
    if output_dir.exists():
        if not overwrite:
            raise FileExistsError(f"{output_dir} already exists. Re-run with --overwrite to rebuild it.")
        shutil.rmtree(output_dir)

    for split in ("train", "val"):
        (output_dir / "images" / split).mkdir(parents=True, exist_ok=True)
        (output_dir / "labels" / split).mkdir(parents=True, exist_ok=True)


def write_data_yaml(output_dir: Path, class_names: dict[int, str]) -> None:
    data = {
        "path": str(output_dir),
        "train": "images/train",
        "val": "images/val",
        "names": {int(class_id): name for class_id, name in sorted(class_names.items())},
    }
    (output_dir / "data.yaml").write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def extract_member(archive: zipfile.ZipFile, member: str, output_path: Path) -> None:
    with archive.open(member) as source_file, output_path.open("wb") as target_file:
        shutil.copyfileobj(source_file, target_file)


def build_dataset(
    archive_path: Path,
    output_dir: Path,
    val_fraction: float,
    seed: int,
    overwrite: bool,
) -> None:
    if not archive_path.exists():
        raise FileNotFoundError(archive_path)
    if not 0.0 < val_fraction < 1.0:
        raise ValueError("--val-fraction must be between 0 and 1")

    with zipfile.ZipFile(archive_path) as archive:
        class_names = read_names(archive)
        items = list_items(archive)

        for item in items:
            if item.label_member is None:
                continue
            label_text = archive.read(item.label_member).decode("utf-8")
            validate_label_text(label_text, item.label_member, class_names)

        split_by_image = stratified_split(items, val_fraction=val_fraction, seed=seed)
        prepare_output(output_dir, overwrite=overwrite)

        manifest_rows: list[dict[str, str | int]] = []
        split_image_paths: dict[str, list[str]] = {"train": [], "val": []}

        for item in sorted(items, key=lambda current_item: current_item.image_member):
            split = split_by_image[item.image_member]
            image_name = Path(item.image_member).name
            label_name = f"{item.stem}.txt"
            image_output = output_dir / "images" / split / image_name
            label_output = output_dir / "labels" / split / label_name

            extract_member(archive, item.image_member, image_output)
            if item.label_member is None:
                label_output.write_text("", encoding="utf-8")
            else:
                label_text = archive.read(item.label_member).decode("utf-8")
                label_output.write_text(label_text, encoding="utf-8")

            split_image_paths[split].append(f"images/{split}/{image_name}")
            manifest_rows.append(
                {
                    "split": split,
                    "image": f"images/{split}/{image_name}",
                    "label": f"labels/{split}/{label_name}",
                    "source_image": item.image_member,
                    "source_label": item.label_member or "",
                    "box_count": item.box_count,
                    "has_objects": int(item.has_objects),
                }
            )

        for split, image_paths in split_image_paths.items():
            (output_dir / f"{split}.txt").write_text("\n".join(image_paths) + "\n", encoding="utf-8")

        with (output_dir / "split_manifest.csv").open("w", newline="", encoding="utf-8") as file:
            fieldnames = [
                "split",
                "image",
                "label",
                "source_image",
                "source_label",
                "box_count",
                "has_objects",
            ]
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(manifest_rows)

        write_data_yaml(output_dir, class_names)

    print(f"Dataset written to: {output_dir}")
    for split in ("train", "val"):
        split_rows = [row for row in manifest_rows if row["split"] == split]
        positive_images = sum(int(row["has_objects"]) for row in split_rows)
        empty_images = len(split_rows) - positive_images
        box_count = sum(int(row["box_count"]) for row in split_rows)
        print(
            f"{split}: images={len(split_rows)}, boxes={box_count}, "
            f"positive_images={positive_images}, empty_images={empty_images}"
        )


def main() -> None:
    args = parse_args()
    archive_path = args.archive.resolve()
    output_dir = args.output.resolve()
    build_dataset(
        archive_path=archive_path,
        output_dir=output_dir,
        val_fraction=args.val_fraction,
        seed=args.seed,
        overwrite=args.overwrite,
    )


if __name__ == "__main__":
    main()
