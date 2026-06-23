#!/usr/bin/env bash
set -euo pipefail

INPUT="${1:-ml/data/pipeline/input/VideoProject.mp4}"
if [[ $# -gt 0 ]]; then
  shift
fi
FRAME_STRIDE="${FRAME_STRIDE:-1}"
DEVICE="${DEVICE:-0}"
DETECTOR_MODEL="${DETECTOR_MODEL:-models/detection/best.pt}"
CLASSIFIER_MODEL="${CLASSIFIER_MODEL:-models/classification/best.pt}"
BRAND_OVERRIDES="${BRAND_OVERRIDES:-ml/pipeline/brand_overrides.csv}"

CMD=(
  .venv/bin/python -m ml.pipeline.run_pipeline
  --input "$INPUT" \
  --detector-model "$DETECTOR_MODEL" \
  --classifier-model "$CLASSIFIER_MODEL" \
  --frame-stride "$FRAME_STRIDE" \
  --device "$DEVICE"
)

if [[ -f "$BRAND_OVERRIDES" ]]; then
  CMD+=(--brand-overrides "$BRAND_OVERRIDES")
fi

CMD+=("$@")

"${CMD[@]}"
