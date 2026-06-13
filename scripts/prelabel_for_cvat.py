from __future__ import annotations

import argparse
import csv
import os
import random
import shutil
import sys
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from PIL import Image, ImageOps


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
DEFAULT_MODEL = (
    "models/trained/yolo11x_scratch_img1280/best.pt"
)


@dataclass(frozen=True)
class PreparedImage:
    path: Path
    cvat_name: str
    original_name: str
    width: int
    height: int


def log(message: str) -> None:
    print(message, flush=True)


def find_project_root(start: Path) -> Path:
    for path in [start.resolve(), *start.resolve().parents]:
        if (path / "pyproject.toml").exists():
            return path
    return start.resolve()


def resolve_path(project_root: Path, path: str | Path) -> Path:
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate
    return project_root / candidate


def find_latest_best_weights(project_root: Path) -> Path:
    weights = sorted(
        (project_root / "runs").rglob("weights/best.pt"),
        key=lambda path: path.stat().st_mtime,
    )
    if not weights:
        raise FileNotFoundError("No weights/best.pt files found under runs/")
    return weights[-1]


def archive_image_members(archive_path: Path) -> list[zipfile.ZipInfo]:
    with zipfile.ZipFile(archive_path) as archive:
        members = []
        for member in archive.infolist():
            member_path = Path(member.filename)
            if member.is_dir():
                continue
            if member_path.is_absolute() or ".." in member_path.parts:
                raise ValueError(f"Unsafe path in zip archive: {member.filename}")
            if member_path.suffix.lower() in IMAGE_EXTENSIONS:
                members.append(member)

    return sorted(members, key=lambda member: member.filename)


def clean_prepare_outputs(normalized_dir: Path, mapping_csv_path: Path, cvat_zip_path: Path) -> None:
    if normalized_dir.exists():
        shutil.rmtree(normalized_dir)
    if mapping_csv_path.exists():
        mapping_csv_path.unlink()
    if cvat_zip_path.exists():
        cvat_zip_path.unlink()


def prepare_images_from_zip(
    *,
    archive_path: Path,
    normalized_dir: Path,
    mapping_csv_path: Path,
    cvat_zip_path: Path,
    name_prefix: str,
    digits: int,
    seed: int,
    jpeg_quality: int,
    clean: bool,
) -> list[PreparedImage]:
    members = archive_image_members(archive_path)
    if not members:
        raise ValueError(f"No images found in archive: {archive_path}")

    rng = random.Random(seed)
    rng.shuffle(members)

    if clean:
        clean_prepare_outputs(normalized_dir, mapping_csv_path, cvat_zip_path)

    normalized_dir.mkdir(parents=True, exist_ok=True)
    mapping_csv_path.parent.mkdir(parents=True, exist_ok=True)
    cvat_zip_path.parent.mkdir(parents=True, exist_ok=True)

    number_width = max(digits, len(str(len(members))))
    prepared_images: list[PreparedImage] = []

    log(f"Archive images: {len(members)}")
    log(f"Shuffle seed: {seed}")
    log(f"Writing normalized images to: {normalized_dir}")

    with zipfile.ZipFile(archive_path) as archive:
        for index, member in enumerate(members, start=1):
            cvat_name = f"{name_prefix}_{index:0{number_width}d}.jpg"
            output_path = normalized_dir / cvat_name

            with archive.open(member) as image_file:
                with Image.open(image_file) as image:
                    image = ImageOps.exif_transpose(image)
                    if image.mode != "RGB":
                        image = image.convert("RGB")
                    image.save(output_path, format="JPEG", quality=jpeg_quality, optimize=True)
                    width, height = image.size

            prepared_images.append(
                PreparedImage(
                    path=output_path,
                    cvat_name=cvat_name,
                    original_name=member.filename,
                    width=width,
                    height=height,
                )
            )

            if index == 1 or index % 25 == 0 or index == len(members):
                log(f"Prepared {index}/{len(members)}")

    with mapping_csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=["cvat_name", "original_name", "width", "height"],
        )
        writer.writeheader()
        for image in prepared_images:
            writer.writerow(
                {
                    "cvat_name": image.cvat_name,
                    "original_name": image.original_name,
                    "width": image.width,
                    "height": image.height,
                }
            )

    with zipfile.ZipFile(cvat_zip_path, "w", compression=zipfile.ZIP_STORED) as archive:
        for image in prepared_images:
            archive.write(image.path, arcname=image.cvat_name)

    log(f"CVAT zip: {cvat_zip_path}")
    log(f"Name mapping: {mapping_csv_path}")
    return prepared_images


def load_prepared_images(normalized_dir: Path, mapping_csv_path: Path) -> list[PreparedImage]:
    if not mapping_csv_path.exists():
        raise FileNotFoundError(f"Mapping CSV not found. Run prepare first: {mapping_csv_path}")

    prepared_images: list[PreparedImage] = []
    with mapping_csv_path.open("r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            cvat_name = row["cvat_name"]
            image_path = normalized_dir / cvat_name
            if not image_path.exists():
                raise FileNotFoundError(f"Prepared image not found: {image_path}")

            prepared_images.append(
                PreparedImage(
                    path=image_path,
                    cvat_name=cvat_name,
                    original_name=row["original_name"],
                    width=int(row["width"]),
                    height=int(row["height"]),
                )
            )

    return prepared_images


def model_class_names(model: Any) -> dict[int, str]:
    names = model.names
    if isinstance(names, dict):
        return {int(class_id): str(name) for class_id, name in names.items()}
    return {idx: str(name) for idx, name in enumerate(names)}


def append_text(parent: ET.Element, tag: str, text: str | int) -> ET.Element:
    child = ET.SubElement(parent, tag)
    child.text = str(text)
    return child


def build_cvat_xml(
    *,
    prepared_images: list[PreparedImage],
    detections_by_image: dict[Path, list[dict[str, float | str]]],
    labels: list[str],
) -> ET.ElementTree:
    now = datetime.now(UTC).isoformat()
    annotations = ET.Element("annotations")
    append_text(annotations, "version", "1.1")

    meta = ET.SubElement(annotations, "meta")
    task = ET.SubElement(meta, "task")
    append_text(task, "id", 0)
    append_text(task, "name", "model_prelabel")
    append_text(task, "size", len(prepared_images))
    append_text(task, "mode", "annotation")
    append_text(task, "overlap", 0)
    append_text(task, "bugtracker", "")
    append_text(task, "created", now)
    append_text(task, "updated", now)
    append_text(task, "subset", "default")
    append_text(task, "start_frame", 0)
    append_text(task, "stop_frame", max(len(prepared_images) - 1, 0))
    append_text(task, "frame_filter", "")

    segments = ET.SubElement(task, "segments")
    segment = ET.SubElement(segments, "segment")
    append_text(segment, "id", 0)
    append_text(segment, "start", 0)
    append_text(segment, "stop", max(len(prepared_images) - 1, 0))
    append_text(segment, "url", "")

    owner = ET.SubElement(task, "owner")
    append_text(owner, "username", "")
    append_text(owner, "email", "")
    append_text(task, "assignee", "")

    labels_node = ET.SubElement(task, "labels")
    for label_name in labels:
        label = ET.SubElement(labels_node, "label")
        append_text(label, "name", label_name)
        append_text(label, "color", "#fa3253")
        append_text(label, "type", "rectangle")
        ET.SubElement(label, "attributes")

    append_text(meta, "dumped", now)

    for image_id, image in enumerate(prepared_images):
        image_node = ET.SubElement(
            annotations,
            "image",
            {
                "id": str(image_id),
                "name": image.cvat_name,
                "width": str(image.width),
                "height": str(image.height),
            },
        )

        for detection in detections_by_image.get(image.path, []):
            ET.SubElement(
                image_node,
                "box",
                {
                    "label": str(detection["label"]),
                    "source": "auto",
                    "occluded": "0",
                    "xtl": f"{float(detection['xtl']):.2f}",
                    "ytl": f"{float(detection['ytl']):.2f}",
                    "xbr": f"{float(detection['xbr']):.2f}",
                    "ybr": f"{float(detection['ybr']):.2f}",
                    "z_order": "0",
                },
            )

    ET.indent(annotations, space="  ")
    return ET.ElementTree(annotations)


def predict_images(
    *,
    model: Any,
    prepared_images: list[PreparedImage],
    conf: float,
    imgsz: int,
    device: str | None,
    label_name: str,
    use_model_labels: bool,
) -> tuple[dict[Path, list[dict[str, float | str]]], list[str]]:
    class_names = model_class_names(model)
    detections_by_image: dict[Path, list[dict[str, float | str]]] = {}
    used_labels: set[str] = set()

    if not use_model_labels:
        used_labels.add(label_name)

    for index, image in enumerate(prepared_images, start=1):
        log(f"[{index}/{len(prepared_images)}] {image.cvat_name}")
        results = model.predict(
            source=str(image.path),
            conf=conf,
            imgsz=imgsz,
            device=device,
            save=False,
            verbose=False,
        )

        image_detections: list[dict[str, float | str]] = []
        result = results[0]
        if result.boxes is None:
            detections_by_image[image.path] = image_detections
            continue

        boxes = result.boxes.xyxy.cpu().tolist()
        classes = result.boxes.cls.cpu().tolist()

        for box, class_id_float in zip(boxes, classes, strict=True):
            class_id = int(class_id_float)
            resolved_label = class_names.get(class_id, str(class_id)) if use_model_labels else label_name

            xtl = max(0.0, min(float(box[0]), float(image.width)))
            ytl = max(0.0, min(float(box[1]), float(image.height)))
            xbr = max(0.0, min(float(box[2]), float(image.width)))
            ybr = max(0.0, min(float(box[3]), float(image.height)))
            if xbr <= xtl or ybr <= ytl:
                continue

            used_labels.add(resolved_label)
            image_detections.append(
                {
                    "label": resolved_label,
                    "xtl": xtl,
                    "ytl": ytl,
                    "xbr": xbr,
                    "ybr": ybr,
                }
            )

        detections_by_image[image.path] = image_detections

    return detections_by_image, sorted(used_labels)


def run_prepare(args: argparse.Namespace, project_root: Path) -> list[PreparedImage]:
    archive_path = resolve_path(project_root, args.archive)
    normalized_dir = resolve_path(project_root, args.normalized_dir)
    mapping_csv_path = resolve_path(project_root, args.mapping_csv)
    cvat_zip_path = resolve_path(project_root, args.cvat_zip)

    if not archive_path.exists():
        raise FileNotFoundError(f"Archive not found: {archive_path}")

    return prepare_images_from_zip(
        archive_path=archive_path,
        normalized_dir=normalized_dir,
        mapping_csv_path=mapping_csv_path,
        cvat_zip_path=cvat_zip_path,
        name_prefix=args.name_prefix,
        digits=args.digits,
        seed=args.seed,
        jpeg_quality=args.jpeg_quality,
        clean=not args.no_clean,
    )


def run_label(args: argparse.Namespace, project_root: Path) -> None:
    normalized_dir = resolve_path(project_root, args.normalized_dir)
    mapping_csv_path = resolve_path(project_root, args.mapping_csv)
    output_path = resolve_path(project_root, args.output)
    model_path = resolve_path(project_root, args.model)

    prepared_images = load_prepared_images(normalized_dir, mapping_csv_path)
    if not model_path.exists():
        fallback_model_path = find_latest_best_weights(project_root)
        log(f"Model not found: {model_path}")
        log(f"Using latest best.pt instead: {fallback_model_path}")
        model_path = fallback_model_path

    log(f"Prepared images: {len(prepared_images)}")
    log(f"Model: {model_path}")
    log(f"Annotations XML: {output_path}")

    os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

    from ultralytics import YOLO

    model = YOLO(str(model_path))
    detections_by_image, labels = predict_images(
        model=model,
        prepared_images=prepared_images,
        conf=args.conf,
        imgsz=args.imgsz,
        device=args.device,
        label_name=args.label_name,
        use_model_labels=args.use_model_labels,
    )

    xml_tree = build_cvat_xml(
        prepared_images=prepared_images,
        detections_by_image=detections_by_image,
        labels=labels,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    xml_tree.write(output_path, encoding="utf-8", xml_declaration=True)

    total_boxes = sum(len(detections) for detections in detections_by_image.values())
    log(f"Done: {output_path}")
    log(f"Images written: {len(prepared_images)}")
    log(f"Boxes written: {total_boxes}")
    log(f"Labels: {', '.join(labels)}")


def add_prepare_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--archive", default="photo.zip", help="Source zip archive with photos.")
    parser.add_argument(
        "--normalized-dir",
        default="data/prelabel/photo/images",
        help="Directory for normalized photo_001.jpg images.",
    )
    parser.add_argument(
        "--mapping-csv",
        default="data/prelabel/photo/name_mapping.csv",
        help="CSV mapping between new CVAT names and original archive names.",
    )
    parser.add_argument(
        "--cvat-zip",
        default="cvat_import/photo_cvat.zip",
        help="Output zip to upload to CVAT when creating the task.",
    )
    parser.add_argument("--name-prefix", default="photo", help="Normalized image name prefix.")
    parser.add_argument("--digits", type=int, default=3, help="Minimum number width: photo_001.jpg.")
    parser.add_argument("--seed", type=int, default=42, help="Deterministic shuffle seed.")
    parser.add_argument("--jpeg-quality", type=int, default=95, help="JPEG quality for normalized images.")
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Do not remove previous prepared images, mapping CSV, and CVAT zip before preparing.",
    )


def add_label_args(parser: argparse.ArgumentParser, include_prepared_paths: bool = True) -> None:
    if include_prepared_paths:
        parser.add_argument(
            "--normalized-dir",
            default="data/prelabel/photo/images",
            help="Directory with normalized photo_001.jpg images.",
        )
        parser.add_argument(
            "--mapping-csv",
            default="data/prelabel/photo/name_mapping.csv",
            help="CSV mapping produced by prepare.",
        )
    parser.add_argument(
        "--output",
        default="cvat_import/photo_annotations.xml",
        help="Output CVAT XML annotation file.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Path to trained YOLO weights. Falls back to latest runs/**/weights/best.pt if missing.",
    )
    parser.add_argument("--conf", type=float, default=0.25, help="YOLO confidence threshold.")
    parser.add_argument("--imgsz", type=int, default=1280, help="YOLO inference image size.")
    parser.add_argument("--device", default=None, help="YOLO device, for example cuda:0 or cpu.")
    parser.add_argument(
        "--label-name",
        default="ad_object",
        help="CVAT label name to use for all detections. Must exist in the CVAT project.",
    )
    parser.add_argument(
        "--use-model-labels",
        action="store_true",
        help="Use class names from the YOLO model instead of --label-name.",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare randomized CVAT-ready images and run YOLO pre-labeling "
            "as two separate steps."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare", help="Randomize, rename, and zip images for CVAT.")
    add_prepare_args(prepare_parser)

    label_parser = subparsers.add_parser("label", help="Run YOLO on prepared images and write CVAT XML.")
    add_label_args(label_parser)

    all_parser = subparsers.add_parser("all", help="Run prepare, then label.")
    add_prepare_args(all_parser)
    add_label_args(all_parser, include_prepared_paths=False)

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = find_project_root(Path.cwd())

    try:
        if args.command == "prepare":
            run_prepare(args, project_root)
        elif args.command == "label":
            run_label(args, project_root)
        elif args.command == "all":
            run_prepare(args, project_root)
            run_label(args, project_root)
        else:
            raise ValueError(f"Unknown command: {args.command}")
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
