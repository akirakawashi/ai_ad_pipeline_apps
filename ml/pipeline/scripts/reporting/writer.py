"""Top-level report artifact writer."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..artifacts import (
    DETECTION_CSV_FIELDS,
    TRACK_CSV_FIELDS,
    DetectionCsvRow,
    TrackCsvRow,
)
from ..schemas import DetectionRecord, InputMetadata, TrackRecord
from .charts import write_charts
from .csv_io import write_dict_csv, write_input_meta
from .html_report import write_html_report
from .summaries import write_summaries


def write_pipeline_outputs(
    output_dir: Path,
    metadata: InputMetadata,
    detections: list[DetectionRecord],
    tracks: list[TrackRecord],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_input_meta(output_dir / "input_meta.json", metadata)
    detections_csv = output_dir / "detections.csv"
    tracks_csv = output_dir / "tracks.csv"
    detection_rows = [
        DetectionCsvRow.model_validate(detection).to_csv_row()
        for detection in detections
    ]
    track_rows = [
        TrackCsvRow.model_validate(track).to_csv_row()
        for track in tracks
    ]
    write_dict_csv(
        detections_csv,
        detection_rows,
        fieldnames=DETECTION_CSV_FIELDS,
    )
    write_dict_csv(
        tracks_csv,
        track_rows,
        fieldnames=TRACK_CSV_FIELDS,
    )

    detections_df = pd.DataFrame(detection_rows)
    tracks_df = pd.DataFrame(track_rows)
    # Автономные отчёты пайплайна оперируют базовой заметностью S·α (β нет —
    # он на бэкенде). Колонку не пишем в tracks.csv, а выводим для отчётов.
    if not tracks_df.empty:
        tracks_df["visibility_value"] = (
            tracks_df["attention_seconds"] * tracks_df["confidence_coef"]
        )
    write_summaries(output_dir, detections_df, tracks_df)
    write_charts(output_dir / "charts", detections_df, tracks_df)
    write_html_report(output_dir / "report.html", metadata, detections_df, tracks_df)
