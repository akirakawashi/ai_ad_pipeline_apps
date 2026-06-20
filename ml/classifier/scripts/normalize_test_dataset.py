#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import random
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
CLASS_FILE_PREFIX = {
    "+7": "plus7",
    "miranda": "miranda",
    "mts": "mts",
    "other": "other",
}
PROJECT_ROOT = Path(__file__).resolve().parents[3]
CLASSIFICATION_DATA_DIR = PROJECT_ROOT / "ml" / "data" / "classification"


@dataclass(frozen=True)
class RenameRecord:
    class_name: str
    original_path: Path
    new_path: Path
    original_extension: str
    converted_to_png: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize classifier/test in-place.")
    parser.add_argument(
        "--source",
        type=Path,
        default=CLASSIFICATION_DATA_DIR / "v2_ads_only" / "test",
        help="Directory with class subdirectories.",
    )
    parser.add_argument("--seed", type=int, default=20260617)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=CLASSIFICATION_DATA_DIR / "v2_ads_only" / "test_normalization_manifest.csv",
    )
    return parser.parse_args()


def remove_zone_identifier_files(source_dir: Path) -> int:
    removed = 0
    for path in sorted(source_dir.rglob("*:Zone.Identifier")):
        if path.is_file():
            path.unlink()
            removed += 1
    return removed


def collect_images(class_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in class_dir.rglob("*")
        if path.is_file() and path.suffix.casefold() in IMAGE_EXTENSIONS
    )


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


def write_png(source_path: Path, output_path: Path) -> bool:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if source_path.suffix.casefold() == ".png":
        shutil.copy2(source_path, output_path)
        return False

    convert_with_ffmpeg(source_path, output_path)
    return True


def remove_empty_subdirs(class_dir: Path) -> None:
    for path in sorted((p for p in class_dir.rglob("*") if p.is_dir()), reverse=True):
        try:
            path.rmdir()
        except OSError:
            pass


def write_manifest(manifest_path: Path, records: list[RenameRecord]) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "class",
                "original_path",
                "new_path",
                "original_extension",
                "converted_to_png",
            ],
        )
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "class": record.class_name,
                    "original_path": record.original_path,
                    "new_path": record.new_path,
                    "original_extension": record.original_extension,
                    "converted_to_png": int(record.converted_to_png),
                }
            )


def main() -> int:
    args = parse_args()
    source_dir = args.source.resolve()

    if not source_dir.exists():
        print(f"Source directory does not exist: {source_dir}", file=sys.stderr)
        return 1

    if not shutil.which("ffmpeg"):
        print("ffmpeg is required for jpg/jpeg/webp to png conversion.", file=sys.stderr)
        return 1

    class_dirs = sorted(path for path in source_dir.iterdir() if path.is_dir())
    if not class_dirs:
        print(f"No class directories found in {source_dir}", file=sys.stderr)
        return 1

    removed_zone_files = remove_zone_identifier_files(source_dir)
    images_by_class = {class_dir: collect_images(class_dir) for class_dir in class_dirs}
    original_total = sum(len(paths) for paths in images_by_class.values())

    tmp_dir = source_dir.parent / ".normalize_test_tmp"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True)

    rng = random.Random(args.seed)
    records: list[RenameRecord] = []

    try:
        for class_dir, image_paths in images_by_class.items():
            class_name = class_dir.name
            shuffled = list(image_paths)
            rng.shuffle(shuffled)
            prefix = CLASS_FILE_PREFIX.get(class_name, class_name.casefold())

            for index, source_path in enumerate(shuffled, start=1):
                output_name = f"{prefix}_{index:06d}.png"
                tmp_path = tmp_dir / class_name / output_name
                final_path = class_dir / output_name
                converted = write_png(source_path, tmp_path)
                records.append(
                    RenameRecord(
                        class_name=class_name,
                        original_path=source_path,
                        new_path=final_path,
                        original_extension=source_path.suffix.casefold(),
                        converted_to_png=converted,
                    )
                )

        tmp_total = len(list(tmp_dir.rglob("*.png")))
        if tmp_total != original_total:
            raise RuntimeError(f"Image count changed before replacement: {original_total} -> {tmp_total}")

        for image_paths in images_by_class.values():
            for path in image_paths:
                path.unlink()

        for class_dir in class_dirs:
            remove_empty_subdirs(class_dir)
            tmp_class_dir = tmp_dir / class_dir.name
            for tmp_path in sorted(tmp_class_dir.glob("*.png")):
                shutil.move(str(tmp_path), class_dir / tmp_path.name)

        final_total = sum(len(collect_images(class_dir)) for class_dir in class_dirs)
        if final_total != original_total:
            raise RuntimeError(f"Image count changed after replacement: {original_total} -> {final_total}")

        write_manifest(args.manifest, records)
    finally:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)

    converted_count = sum(record.converted_to_png for record in records)
    print(f"Removed Zone.Identifier files: {removed_zone_files}")
    print(f"Images kept: {original_total}")
    print(f"Converted to PNG: {converted_count}")
    print(f"Manifest: {args.manifest.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
