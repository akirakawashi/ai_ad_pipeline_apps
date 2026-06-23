"""Brand classification helpers."""

from __future__ import annotations

from dataclasses import dataclass

import timm
import torch
from PIL import Image, ImageOps
from torchvision import transforms

from .config import PipelineConfig
from .domain import (
    BrandStatus,
    ClassificationInputStatus,
    CropQualityStatus,
    FinalStatus,
    normalize_brand_name,
)
from .schemas import DetectionRecord


class ResizePad:
    def __init__(self, size: int, fill: tuple[int, int, int] = (0, 0, 0)) -> None:
        self.size = size
        self.fill = fill

    def __call__(self, image: Image.Image) -> Image.Image:
        contained = ImageOps.contain(
            image, (self.size, self.size), Image.Resampling.BICUBIC
        )
        canvas = Image.new("RGB", (self.size, self.size), self.fill)
        offset = (
            (self.size - contained.width) // 2,
            (self.size - contained.height) // 2,
        )
        canvas.paste(contained, offset)
        return canvas


@dataclass
class BrandClassifier:
    model: torch.nn.Module
    classes: list[str]
    transform: transforms.Compose
    device: torch.device


def load_classifier(config: PipelineConfig) -> BrandClassifier:
    if not config.classifier_model_path.exists():
        raise FileNotFoundError(config.classifier_model_path)

    checkpoint = torch.load(config.classifier_model_path, map_location="cpu")
    args = checkpoint.get("args", {})
    classes = [normalize_brand_name(value) for value in checkpoint["classes"]]
    model_name = args.get("model", "convnext_tiny.fb_in22k_ft_in1k")
    input_size = int(args.get("input_size", 500))

    device = torch.device(normalize_torch_device(config.device))
    model = timm.create_model(model_name, pretrained=False, num_classes=len(classes))
    model.load_state_dict(checkpoint["model_state"])
    model.to(device)
    model.eval()

    transform = transforms.Compose(
        [
            ResizePad(input_size),
            transforms.ToTensor(),
            transforms.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
        ]
    )
    return BrandClassifier(
        model=model, classes=classes, transform=transform, device=device
    )


def classify_detections(
    classifier: BrandClassifier,
    detections: list[DetectionRecord],
    config: PipelineConfig,
) -> None:
    eligible = [
        detection
        for detection in detections
        if detection.crop_path
        and detection.crop_quality_status
        in {CropQualityStatus.PASSED, CropQualityStatus.BORDERLINE}
        and detection.classification_input_status
        in {
            ClassificationInputStatus.ACCEPTED,
            ClassificationInputStatus.BORDERLINE,
        }
    ]
    selected = select_best_detections_by_object(
        eligible, config.classification.best_crops_per_object
    )

    with torch.no_grad():
        for detection in selected:
            with Image.open(detection.crop_path) as source:
                image = source.convert("RGB")
            tensor = classifier.transform(image).unsqueeze(0).to(classifier.device)
            logits = classifier.model(tensor)
            probabilities = torch.softmax(logits, dim=1)[0].detach().cpu()
            top_scores, top_indices = torch.topk(
                probabilities, k=min(3, len(classifier.classes))
            )
            top = [
                (classifier.classes[int(index)], float(score))
                for score, index in zip(top_scores.tolist(), top_indices.tolist())
            ]
            _fill_detection_prediction(detection, top, config)


def select_best_detections_by_object(
    detections: list[DetectionRecord],
    per_object: int,
) -> list[DetectionRecord]:
    grouped: dict[tuple[str, int], list[DetectionRecord]] = {}
    for detection in detections:
        group_key = detection_group_key(detection)
        if group_key is None:
            continue
        grouped.setdefault(group_key, []).append(detection)

    selected: list[DetectionRecord] = []
    for object_detections in grouped.values():
        ordered = sorted(object_detections, key=best_crop_score, reverse=True)
        selected.extend(ordered[:per_object])
    return selected


def detection_group_key(detection: DetectionRecord) -> tuple[str, int] | None:
    if detection.object_id is not None:
        return ("object", detection.object_id)
    if detection.track_id is not None:
        return ("track", detection.track_id)
    return None


def best_crop_score(detection: DetectionRecord) -> float:
    return detection.crop_quality_score * detection.area_ratio * detection.det_conf


def normalize_torch_device(value: str | None) -> str:
    if value is None or value == "":
        return "cuda" if torch.cuda.is_available() else "cpu"
    normalized = str(value).strip()
    if normalized.isdigit():
        return f"cuda:{normalized}"
    if "," in normalized and all(
        part.strip().isdigit() for part in normalized.split(",")
    ):
        return f"cuda:{normalized.split(',', maxsplit=1)[0].strip()}"
    return normalized


def _fill_detection_prediction(
    detection: DetectionRecord,
    top: list[tuple[str, float]],
    config: PipelineConfig,
) -> None:
    detection.classification_attempted = True
    if not top:
        detection.brand_status = BrandStatus.UNKNOWN
        detection.final_status = FinalStatus.UNKNOWN
        detection.status_reason = "brand_conf_low"
        return

    detection.top1_brand, detection.top1_score = top[0]
    detection.brand_pred = detection.top1_brand
    detection.brand_conf = detection.top1_score
    if detection.brand_pred == "other":
        if detection.brand_conf >= config.classification.other_confidence_accept:
            detection.brand_status = BrandStatus.OTHER
        elif detection.brand_conf >= config.classification.manual_review_min:
            detection.brand_status = BrandStatus.MANUAL_REVIEW
        else:
            detection.brand_status = BrandStatus.UNKNOWN
    elif detection.brand_conf >= config.classification.brand_confidence_accept:
        detection.brand_status = BrandStatus.DETECTED_BRAND
    elif detection.brand_conf >= config.classification.manual_review_min:
        detection.brand_status = BrandStatus.MANUAL_REVIEW
    else:
        detection.brand_status = BrandStatus.UNKNOWN

    if len(top) > 1:
        detection.top2_brand, detection.top2_score = top[1]
    if len(top) > 2:
        detection.top3_brand, detection.top3_score = top[2]
