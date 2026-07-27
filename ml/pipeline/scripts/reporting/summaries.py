"""CSV summary builders for detections and track objects."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..artifacts import (
    BRAND_DETECTION_SUMMARY_FIELDS,
    BRAND_TRACK_SUMMARY_FIELDS,
    FRAME_SUMMARY_FIELDS,
)
from .common import filter_business_visible
from .csv_io import write_dict_csv


def write_summaries(
    output_dir: Path, detections_df: pd.DataFrame, tracks_df: pd.DataFrame
) -> None:
    visible_detections_df = filter_business_visible(detections_df)
    visible_tracks_df = filter_business_visible(tracks_df)

    if visible_detections_df.empty:
        write_dict_csv(
            output_dir / "brand_summary_by_detections.csv",
            [],
            fieldnames=BRAND_DETECTION_SUMMARY_FIELDS,
        )
        write_dict_csv(
            output_dir / "frame_summary.csv",
            [],
            fieldnames=FRAME_SUMMARY_FIELDS,
        )
    else:
        detection_summary = (
            visible_detections_df.groupby(["business_brand"], dropna=False)
            .agg(
                detection_count=("det_index", "count"),
                mean_brand_conf=("brand_conf", "mean"),
                max_brand_conf=("brand_conf", "max"),
                first_timestamp_sec=("timestamp_sec", "min"),
                last_timestamp_sec=("timestamp_sec", "max"),
                sum_intensity=("intensity", "sum"),
            )
            .reset_index()
            .rename(columns={"business_brand": "brand"})
        )
        detection_summary.to_csv(
            output_dir / "brand_summary_by_detections.csv", index=False
        )

        frame_summary = (
            visible_detections_df.groupby(
                ["frame_index", "timestamp_sec"], dropna=False
            )
            .agg(
                detections_total=("det_index", "count"),
                mts_count=("business_brand", lambda s: int((s == "mts").sum())),
                plus7_count=("business_brand", lambda s: int((s == "plus7").sum())),
                miranda_count=("business_brand", lambda s: int((s == "miranda").sum())),
                other_count=("business_brand", lambda s: int((s == "other").sum())),
                sum_intensity=("intensity", "sum"),
            )
            .reset_index()
        )
        frame_summary.to_csv(output_dir / "frame_summary.csv", index=False)

    if visible_tracks_df.empty:
        write_dict_csv(
            output_dir / "brand_summary_by_tracks.csv",
            [],
            fieldnames=BRAND_TRACK_SUMMARY_FIELDS,
        )
        return

    object_df = (
        visible_tracks_df.groupby(["object_id", "business_brand"], dropna=False)
        .agg(
            track_fragment_count=("track_id", "count"),
            sum_visibility_value=("visibility_value", "sum"),
            sum_attention_seconds=("attention_seconds", "sum"),
            mean_final_brand_conf=("final_brand_conf", "mean"),
            max_final_brand_conf=("final_brand_conf", "max"),
            first_timestamp_sec=("first_timestamp_sec", "min"),
            last_timestamp_sec=("last_timestamp_sec", "max"),
        )
        .reset_index()
    )
    track_summary = (
        object_df.groupby(["business_brand"], dropna=False)
        .agg(
            object_count=("object_id", "count"),
            track_fragment_count=("track_fragment_count", "sum"),
            sum_visibility_value=("sum_visibility_value", "sum"),
            sum_attention_seconds=("sum_attention_seconds", "sum"),
            mean_final_brand_conf=("mean_final_brand_conf", "mean"),
            max_final_brand_conf=("max_final_brand_conf", "max"),
            first_timestamp_sec=("first_timestamp_sec", "min"),
            last_timestamp_sec=("last_timestamp_sec", "max"),
        )
        .reset_index()
        .rename(columns={"business_brand": "brand"})
    )
    track_summary.to_csv(output_dir / "brand_summary_by_tracks.csv", index=False)
