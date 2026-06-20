from __future__ import annotations

import argparse
import csv
import re
import shutil
import time
import zipfile
from pathlib import Path


DEFAULT_MINING_DIR = (
    "outputs/videos/"
    "yolo11m_pretrained_img960_b10_antifp_full_v1_test_rotated_ccw_90/"
    "cvat_mining_conf055_step5"
)


FRAME_RE = re.compile(r"^frame_(\d+)_")


def find_project_root(start: Path | None = None) -> Path:
    start = (start or Path.cwd()).resolve()
    for path in (start, *start.parents):
        if (path / "pyproject.toml").exists() and (path / "ml/ad_detection").exists():
            return path
    raise FileNotFoundError("Could not find ad_detection project root")


def resolve_project_path(project_root: Path, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return project_root / path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Keep only selected CVAT mining frames and move the rest aside."
    )
    parser.add_argument("--mining-dir", default=DEFAULT_MINING_DIR, help="CVAT mining output directory.")
    parser.add_argument("--keep-list", required=True, help="Text file with image/preview names to keep.")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without changing files.")
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Delete removed files instead of moving them into discarded_<timestamp>.",
    )
    parser.add_argument("--no-zip", action="store_true", help="Do not rebuild cvat_images.zip.")
    return parser.parse_args()


def normalize_keep_name(line: str) -> str | None:
    value = line.strip()
    if not value or value.startswith("#"):
        return None
    name = Path(value).name
    suffix = Path(name).suffix.lower()
    if suffix == ".txt":
        return f"{Path(name).stem}.jpg"
    if suffix in {".jpg", ".jpeg", ".png"}:
        return name
    if suffix:
        return name
    return f"{name}.jpg"


def read_keep_list(path: Path) -> set[str]:
    keep = set()
    for line in path.read_text().splitlines():
        name = normalize_keep_name(line)
        if name:
            keep.add(name)
    return keep


def frame_index_from_name(name: str) -> int | None:
    match = FRAME_RE.match(Path(name).stem)
    if not match:
        return None
    return int(match.group(1))


def move_or_delete(path: Path, root: Path, discard_root: Path, delete: bool, dry_run: bool) -> None:
    if dry_run:
        return
    if delete:
        path.unlink()
        return

    relative = path.relative_to(root)
    target = discard_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), str(target))


def filter_files(
    directory: Path,
    keep_names: set[str],
    root: Path,
    discard_root: Path,
    delete: bool,
    dry_run: bool,
    suffixes: set[str],
) -> tuple[int, int]:
    kept = 0
    removed = 0
    for path in sorted(directory.iterdir()):
        if not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        if path.name in keep_names:
            kept += 1
            continue
        move_or_delete(path, root, discard_root, delete, dry_run)
        removed += 1
    return kept, removed


def filter_label_files(
    directory: Path,
    keep_stems: set[str],
    root: Path,
    discard_root: Path,
    delete: bool,
    dry_run: bool,
) -> tuple[int, int]:
    kept = 0
    removed = 0
    for path in sorted(directory.glob("*.txt")):
        if path.stem in keep_stems:
            kept += 1
            continue
        move_or_delete(path, root, discard_root, delete, dry_run)
        removed += 1
    return kept, removed


def row_belongs_to_keep(row: dict[str, str], keep_names: set[str], keep_frames: set[int]) -> bool:
    for key in ("image", "preview"):
        value = row.get(key)
        if value and Path(value).name in keep_names:
            return True

    pred_label = row.get("pred_label")
    if pred_label and f"{Path(pred_label).stem}.jpg" in keep_names:
        return True

    frame = row.get("frame")
    if frame not in (None, ""):
        try:
            return int(float(frame)) in keep_frames
        except ValueError:
            return False
    return False


def filter_csv(path: Path, keep_names: set[str], keep_frames: set[int], dry_run: bool) -> tuple[int, int]:
    if not path.exists():
        return 0, 0

    with path.open(newline="") as file:
        reader = csv.DictReader(file)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    kept_rows = [row for row in rows if row_belongs_to_keep(row, keep_names, keep_frames)]
    removed = len(rows) - len(kept_rows)
    if dry_run:
        return len(kept_rows), removed

    backup = path.with_suffix(f".before_filter_{int(time.time())}{path.suffix}")
    shutil.copy2(path, backup)

    with path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(kept_rows)

    return len(kept_rows), removed


def rebuild_images_zip(images_dir: Path, zip_path: Path, discard_root: Path, dry_run: bool) -> int:
    image_paths = sorted(path for path in images_dir.iterdir() if path.is_file() and path.suffix.lower() == ".jpg")
    if dry_run:
        return len(image_paths)

    if zip_path.exists():
        discard_root.mkdir(parents=True, exist_ok=True)
        backup = discard_root / f"{zip_path.stem}.before_filter_{int(time.time())}{zip_path.suffix}"
        shutil.move(str(zip_path), str(backup))

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for image_path in image_paths:
            archive.write(image_path, arcname=image_path.name)
    return len(image_paths)


def main() -> None:
    args = parse_args()
    project_root = find_project_root(Path(__file__))
    mining_dir = resolve_project_path(project_root, args.mining_dir).resolve()
    keep_list = resolve_project_path(project_root, args.keep_list).resolve()

    images_dir = mining_dir / "images"
    previews_dir = mining_dir / "previews"
    labels_dir = mining_dir / "labels_pred_yolo"
    selected_frames_csv = mining_dir / "selected_frames.csv"
    detections_all_csv = mining_dir / "detections_all.csv"
    cvat_zip = mining_dir / "cvat_images.zip"
    discard_root = mining_dir / f"discarded_{int(time.time())}"

    if not mining_dir.exists():
        raise FileNotFoundError(mining_dir)
    if not keep_list.exists():
        raise FileNotFoundError(keep_list)

    keep_names = read_keep_list(keep_list)
    keep_stems = {Path(name).stem for name in keep_names}
    keep_frames = {frame for name in keep_names if (frame := frame_index_from_name(name)) is not None}

    existing_images = {path.name for path in images_dir.glob("*.jpg")}
    missing_images = sorted(keep_names - existing_images)
    extra_keep_duplicates = len(keep_names) - len(keep_stems)

    print(f"mining dir:      {mining_dir}")
    print(f"keep list:       {keep_list}")
    print(f"keep requested:  {len(keep_names)}")
    print(f"missing images:  {len(missing_images)}")
    if extra_keep_duplicates:
        print(f"duplicate stems: {extra_keep_duplicates}")
    if missing_images:
        print("missing:")
        for name in missing_images:
            print(f"  {name}")
        raise FileNotFoundError("Some requested keep images were not found")

    image_kept, image_removed = filter_files(
        images_dir,
        keep_names,
        mining_dir,
        discard_root,
        args.delete,
        args.dry_run,
        {".jpg", ".jpeg", ".png"},
    )
    preview_kept, preview_removed = filter_files(
        previews_dir,
        keep_names,
        mining_dir,
        discard_root,
        args.delete,
        args.dry_run,
        {".jpg", ".jpeg", ".png"},
    )
    label_kept, label_removed = filter_label_files(
        labels_dir,
        keep_stems,
        mining_dir,
        discard_root,
        args.delete,
        args.dry_run,
    )

    selected_kept, selected_removed = filter_csv(selected_frames_csv, keep_names, keep_frames, args.dry_run)
    detections_kept, detections_removed = filter_csv(detections_all_csv, keep_names, keep_frames, args.dry_run)

    zip_count = 0
    if not args.no_zip:
        zip_count = rebuild_images_zip(images_dir, cvat_zip, discard_root, args.dry_run)

    mode = "dry-run" if args.dry_run else ("delete" if args.delete else f"move to {discard_root}")
    print(f"mode:           {mode}")
    print(f"images:         kept={image_kept}, removed={image_removed}")
    print(f"previews:       kept={preview_kept}, removed={preview_removed}")
    print(f"labels:         kept={label_kept}, removed={label_removed}")
    print(f"selected csv:   kept={selected_kept}, removed={selected_removed}")
    print(f"detections csv: kept={detections_kept}, removed={detections_removed}")
    if not args.no_zip:
        print(f"zip images:     {zip_count}")


if __name__ == "__main__":
    main()
