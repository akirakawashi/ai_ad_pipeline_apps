"""CSV summary builders for detections and track objects."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .common import filter_business_visible
from .csv_io import write_dict_csv


def write_summaries(
    output_dir: Path, detections_df: pd.DataFrame, tracks_df: pd.DataFrame
) -> None:
    visible_detections_df = filter_business_visible(detections_df)
    visible_tracks_df = filter_business_visible(tracks_df)

    if visible_detections_df.empty:
        write_dict_csv(output_dir / "brand_summary_by_detections.csv", [])
        write_dict_csv(output_dir / "frame_summary.csv", [])
    else:
        detection_summary = (
            visible_detections_df.groupby(["business_brand"], dropna=False)
            .agg(
                detection_count=("det_index", "count"),
                mean_brand_conf=("brand_conf", "mean"),
                max_brand_conf=("brand_conf", "max"),
                first_timestamp_sec=("timestamp_sec", "min"),
                last_timestamp_sec=("timestamp_sec", "max"),
                sum_video_visibility_score=("video_visibility_score", "sum"),
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
                sum_video_visibility_score=("video_visibility_score", "sum"),
            )
            .reset_index()
        )
        frame_summary.to_csv(output_dir / "frame_summary.csv", index=False)

    if visible_tracks_df.empty:
        write_dict_csv(output_dir / "brand_summary_by_tracks.csv", [])
        return

    object_df = (
        visible_tracks_df.groupby(["object_id", "business_brand"], dropna=False)
        .agg(
            track_fragment_count=("track_id", "count"),
            mean_track_final_score=("track_final_score", "mean"),
            mean_video_visibility_score=("mean_video_visibility_score", "mean"),
            sum_video_visibility_score=("sum_video_visibility_score", "sum"),
            video_visibility_weighted_seconds=(
                "video_visibility_weighted_seconds",
                "sum",
            ),
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
            mean_track_final_score=("mean_track_final_score", "mean"),
            mean_video_visibility_score=("mean_video_visibility_score", "mean"),
            sum_video_visibility_score=("sum_video_visibility_score", "sum"),
            video_visibility_weighted_seconds=(
                "video_visibility_weighted_seconds",
                "sum",
            ),
            mean_final_brand_conf=("mean_final_brand_conf", "mean"),
            max_final_brand_conf=("max_final_brand_conf", "max"),
            first_timestamp_sec=("first_timestamp_sec", "min"),
            last_timestamp_sec=("last_timestamp_sec", "max"),
        )
        .reset_index()
        .rename(columns={"business_brand": "brand"})
    )
    track_summary.to_csv(output_dir / "brand_summary_by_tracks.csv", index=False)
