#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
IMPORTANT_DIR_NAMES = {"важно", "важное", "важные"}
CLASS_FILE_PREFIX = {
    "+7": "plus7",
    "miranda": "miranda",
    "mts": "mts",
    "other": "other",
}
PROJECT_ROOT = Path(__file__).resolve().parents[3]
CLASSIFICATION_DATA_DIR = PROJECT_ROOT / "ml" / "data" / "classification"


@dataclass(frozen=True)
class ImageRecord:
    class_name: str
    source_path: Path
    is_important: bool
    sha256: str


@dataclass(frozen=True)
class OutputRecord:
    split: str
    class_name: str
    output_path: Path
    source_path: Path
    original_extension: str
    is_important: bool
    sha256: str
    converted_to_png: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare classifier image dataset.")
    parser.add_argument(
        "--source",
        type=Path,
        default=CLASSIFICATION_DATA_DIR / "v2_ads_only" / "test",
        help="Source directory with class subdirectories.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=CLASSIFICATION_DATA_DIR / "v2_ads_only" / "prepared",
        help="Output directory for prepared train/val dataset.",
    )
    parser.add_argument("--seed", type=int, default=20260617)
    parser.add_argument(
        "--target-val-ratio",
        type=float,
        default=0.3,
        help="Validation ratio for target classes.",
    )
    parser.add_argument(
        "--other-val-ratio",
        type=float,
        default=0.5,
        help="Validation ratio for the other class.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Remove output directory before writing.",
    )
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def remove_zone_identifier_files(source_dir: Path) -> list[Path]:
    removed: list[Path] = []
    for path in sorted(source_dir.rglob("*:Zone.Identifier")):
        if path.is_file():
            path.unlink()
            removed.append(path)
    return removed


def is_important_path(class_dir: Path, image_path: Path) -> bool:
    relative_parts = image_path.relative_to(class_dir).parts[:-1]
    return any(part.casefold() in IMPORTANT_DIR_NAMES for part in relative_parts)


def collect_images(source_dir: Path) -> tuple[dict[str, list[ImageRecord]], list[dict[str, str]]]:
    classes: dict[str, list[ImageRecord]] = {}
    duplicates: list[dict[str, str]] = []

    for class_dir in sorted(path for path in source_dir.iterdir() if path.is_dir()):
        class_name = class_dir.name
        seen_by_hash: dict[str, ImageRecord] = {}
        records: list[ImageRecord] = []

        source_paths = sorted(
            path
            for path in class_dir.rglob("*")
            if path.is_file() and path.suffix.casefold() in IMAGE_EXTENSIONS
        )
        source_paths.sort(key=lambda path: (not is_important_path(class_dir, path), str(path)))

        for source_path in source_paths:
            digest = sha256_file(source_path)
            is_important = is_important_path(class_dir, source_path)
            record = ImageRecord(class_name, source_path, is_important, digest)

            if digest in seen_by_hash:
                kept = seen_by_hash[digest]
                duplicates.append(
                    {
                        "class": class_name,
                        "kept_original": str(kept.source_path),
                        "skipped_original": str(source_path),
                        "sha256": digest,
                    }
                )
                continue

            seen_by_hash[digest] = record
            records.append(record)

        classes[class_name] = records

    return classes, duplicates


def split_records(
    classes: dict[str, list[ImageRecord]],
    seed: int,
    target_val_ratio: float,
    other_val_ratio: float,
) -> dict[str, dict[str, list[ImageRecord]]]:
    rng = random.Random(seed)
    split: dict[str, dict[str, list[ImageRecord]]] = {}

    for class_name, records in classes.items():
        regular = [record for record in records if not record.is_important]
        important = [record for record in records if record.is_important]
        rng.shuffle(regular)
        rng.shuffle(important)

        val_ratio = other_val_ratio if class_name == "other" else target_val_ratio
        if regular:
            val_count = max(1, round(len(regular) * val_ratio))
        else:
            val_count = 0

        val_records = regular[:val_count]
        train_records = regular[val_count:] + important
        rng.shuffle(train_records)

        split[class_name] = {
            "train": train_records,
            "val": val_records,
        }

    return split


def convert_with_ffmpeg(source_path: Path, output_path: Path) -> None:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source_path),
        "-frames:v",
        "1",
        str(output_path),
    ]
    subprocess.run(command, check=True)


def write_image(source_path: Path, output_path: Path) -> bool:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if source_path.suffix.casefold() == ".png":
        shutil.copy2(source_path, output_path)
        return False

    convert_with_ffmpeg(source_path, output_path)
    return True


def prepare_output_dir(output_dir: Path, overwrite: bool) -> None:
    if output_dir.exists():
        if not overwrite:
            raise FileExistsError(
                f"{output_dir} already exists. Re-run with --overwrite to replace it."
            )
        shutil.rmtree(output_dir)

    output_dir.mkdir(parents=True)


def write_manifest(output_dir: Path, records: list[OutputRecord]) -> None:
    manifest_path = output_dir / "manifest.csv"
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "split",
                "class",
                "file_path",
                "original_path",
                "original_extension",
                "is_important",
                "sha256",
                "converted_to_png",
            ],
        )
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "split": record.split,
                    "class": record.class_name,
                    "file_path": record.output_path.relative_to(output_dir),
                    "original_path": record.source_path,
                    "original_extension": record.original_extension,
                    "is_important": int(record.is_important),
                    "sha256": record.sha256,
                    "converted_to_png": int(record.converted_to_png),
                }
            )


def write_duplicate_report(output_dir: Path, duplicates: list[dict[str, str]]) -> None:
    report_path = output_dir / "skipped_duplicates.csv"
    with report_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["class", "kept_original", "skipped_original", "sha256"],
        )
        writer.writeheader()
        writer.writerows(duplicates)


def write_important_list(output_dir: Path, records: list[OutputRecord]) -> None:
    important_path = output_dir / "important_train_files.txt"
    with important_path.open("w", encoding="utf-8") as handle:
        for record in records:
            if record.split == "train" and record.is_important:
                handle.write(f"{record.output_path.relative_to(output_dir)}\n")


def write_summary(
    output_dir: Path,
    source_dir: Path,
    seed: int,
    target_val_ratio: float,
    other_val_ratio: float,
    removed_zone_files: list[Path],
    duplicates: list[dict[str, str]],
    records: list[OutputRecord],
) -> None:
    by_class: dict[str, dict[str, int]] = {}
    for record in records:
        class_summary = by_class.setdefault(
            record.class_name,
            {
                "train": 0,
                "val": 0,
                "train_important": 0,
                "val_important": 0,
                "converted_to_png": 0,
            },
        )
        class_summary[record.split] += 1
        if record.is_important:
            class_summary[f"{record.split}_important"] += 1
        if record.converted_to_png:
            class_summary["converted_to_png"] += 1

    summary = {
        "source": str(source_dir),
        "seed": seed,
        "val_ratios": {
            "target_classes": target_val_ratio,
            "other": other_val_ratio,
        },
        "main_format": "png",
        "removed_zone_identifier_files": len(removed_zone_files),
        "skipped_duplicate_files": len(duplicates),
        "total_output_images": len(records),
        "classes": by_class,
    }

    summary_path = output_dir / "summary.json"
    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def main() -> int:
    args = parse_args()

    if not args.source.exists():
        print(f"Source directory does not exist: {args.source}", file=sys.stderr)
        return 1

    if not shutil.which("ffmpeg"):
        print("ffmpeg is required for jpg/jpeg/webp to png conversion.", file=sys.stderr)
        return 1

    removed_zone_files = remove_zone_identifier_files(args.source)
    classes, duplicates = collect_images(args.source)
    split = split_records(
        classes,
        args.seed,
        args.target_val_ratio,
        args.other_val_ratio,
    )
    prepare_output_dir(args.output, args.overwrite)

    output_records: list[OutputRecord] = []
    for split_name in ("train", "val"):
        for class_name in sorted(split):
            prefix = CLASS_FILE_PREFIX.get(class_name, class_name.casefold())
            for index, record in enumerate(split[class_name][split_name], start=1):
                output_name = f"{prefix}_{split_name}_{index:06d}.png"
                output_path = args.output / split_name / class_name / output_name
                converted = write_image(record.source_path, output_path)
                output_records.append(
                    OutputRecord(
                        split=split_name,
                        class_name=class_name,
                        output_path=output_path,
                        source_path=record.source_path,
                        original_extension=record.source_path.suffix.casefold(),
                        is_important=record.is_important,
                        sha256=record.sha256,
                        converted_to_png=converted,
                    )
                )

    write_manifest(args.output, output_records)
    write_duplicate_report(args.output, duplicates)
    write_important_list(args.output, output_records)
    write_summary(
        args.output,
        args.source,
        args.seed,
        args.target_val_ratio,
        args.other_val_ratio,
        removed_zone_files,
        duplicates,
        output_records,
    )

    print(f"Removed Zone.Identifier files: {len(removed_zone_files)}")
    print(f"Skipped duplicate files: {len(duplicates)}")
    print(f"Prepared images: {len(output_records)}")
    print(f"Output: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
