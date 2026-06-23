"""Static HTML report writer."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

import pandas as pd

from ..schemas import InputMetadata
from .common import filter_business_visible


def write_html_report(
    path: Path,
    metadata: InputMetadata,
    detections_df: pd.DataFrame,
    tracks_df: pd.DataFrame,
) -> None:
    title = f"Ad visibility report: {metadata.source_path.name}"
    parts = [
        "<!doctype html>",
        "<html><head><meta charset='utf-8'>",
        f"<title>{html.escape(title)}</title>",
        "<style>body{font-family:Arial,sans-serif;max-width:1200px;margin:32px auto;line-height:1.4}"
        "table{border-collapse:collapse;width:100%;margin:16px 0}th,td{border:1px solid #ddd;padding:6px}"
        "th{background:#f5f5f5}.gallery{display:flex;gap:12px;flex-wrap:wrap}.card{width:180px}"
        ".card img{max-width:180px;max-height:140px;object-fit:contain;border:1px solid #ddd}</style>",
        "</head><body>",
        f"<h1>{html.escape(title)}</h1>",
        "<h2>Input</h2>",
        table_from_rows(
            [
                {"field": "source", "value": str(metadata.source_path)},
                {"field": "input_type", "value": metadata.input_type},
                {"field": "fps", "value": f"{metadata.fps:.3f}"},
                {"field": "frame_count", "value": metadata.frame_count},
                {"field": "frame_stride", "value": metadata.frame_stride},
                {"field": "delta_t_sec", "value": f"{metadata.delta_t_sec:.3f}"},
            ]
        ),
    ]

    parts.append("<h2>Track/Object Summary</h2>")
    visible_tracks_df = filter_business_visible(tracks_df)
    visible_detections_df = filter_business_visible(detections_df)
    if visible_tracks_df.empty:
        parts.append("<p>No tracks found.</p>")
    else:
        display_columns = [
            "object_id",
            "track_id",
            "business_brand",
            "first_timestamp_sec",
            "last_timestamp_sec",
            "visible_duration_sec",
            "detections_count",
            "final_brand_conf",
            "track_final_score",
            "video_visibility_weighted_seconds",
            "best_crop_path",
        ]
        parts.append(
            table_from_rows(
                visible_tracks_df[display_columns].head(50).to_dict("records")
            )
        )

    parts.append("<h2>Detection Summary</h2>")
    if visible_detections_df.empty:
        parts.append("<p>No detections found.</p>")
    else:
        brand_counts = (
            visible_detections_df["business_brand"].value_counts().reset_index()
        )
        brand_counts.columns = ["brand", "count"]
        parts.append(table_from_rows(brand_counts.to_dict("records")))

    parts.extend(["</body></html>"])
    path.write_text("\n".join(parts), encoding="utf-8")


def table_from_rows(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "<p>No rows.</p>"
    columns = list(rows[0].keys())
    html_rows = ["<table><thead><tr>"]
    html_rows.extend(f"<th>{html.escape(str(column))}</th>" for column in columns)
    html_rows.append("</tr></thead><tbody>")
    for row in rows:
        html_rows.append("<tr>")
        html_rows.extend(
            f"<td>{html.escape(str(row.get(column, '')))}</td>" for column in columns
        )
        html_rows.append("</tr>")
    html_rows.append("</tbody></table>")
    return "".join(html_rows)
