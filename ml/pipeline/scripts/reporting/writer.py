"""Top-level report artifact writer."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

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
    detection_rows = [detection.to_row() for detection in detections]
    track_rows = [track.to_row() for track in tracks]
    write_dict_csv(detections_csv, detection_rows)
    write_dict_csv(tracks_csv, track_rows)

    detections_df = pd.DataFrame(detection_rows)
    tracks_df = pd.DataFrame(track_rows)
    write_summaries(output_dir, detections_df, tracks_df)
    write_charts(output_dir / "charts", detections_df, tracks_df)
    write_html_report(output_dir / "report.html", metadata, detections_df, tracks_df)
