"""CSV, chart, and HTML report helpers."""

from __future__ import annotations

import csv
import html
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from scripts.schemas import DetectionRecord, InputMetadata, TrackRecord


BRAND_LABELS = {
    "mts": "МТС",
    "miranda": "Миранда",
    "plus7": "+7",
    "other": "Другая реклама",
}
BRAND_COLORS = {
    "mts": "#ff3b30",
    "miranda": "#22c55e",
    "plus7": "#38bdf8",
    "other": "#facc15",
}
BRAND_ORDER = ["mts", "miranda", "plus7", "other"]
TARGET_BRANDS = ["mts", "miranda", "plus7"]
TIMELINE_BUCKET_SECONDS = 10


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
    write_dict_csv(detections_csv, [detection.to_row() for detection in detections])
    write_dict_csv(tracks_csv, [track.to_row() for track in tracks])

    detections_df = pd.DataFrame([detection.to_row() for detection in detections])
    tracks_df = pd.DataFrame([track.to_row() for track in tracks])
    write_summaries(output_dir, detections_df, tracks_df)
    write_charts(output_dir / "charts", detections_df, tracks_df)
    write_html_report(output_dir / "report.html", metadata, detections_df, tracks_df)


def write_input_meta(path: Path, metadata: InputMetadata) -> None:
    row = asdict(metadata)
    row["source_path"] = str(metadata.source_path)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(row, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def write_dict_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_summaries(output_dir: Path, detections_df: pd.DataFrame, tracks_df: pd.DataFrame) -> None:
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
        detection_summary.to_csv(output_dir / "brand_summary_by_detections.csv", index=False)

        frame_summary = (
            visible_detections_df.groupby(["frame_index", "timestamp_sec"], dropna=False)
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
            video_visibility_weighted_seconds=("video_visibility_weighted_seconds", "sum"),
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
            video_visibility_weighted_seconds=("video_visibility_weighted_seconds", "sum"),
            mean_final_brand_conf=("mean_final_brand_conf", "mean"),
            max_final_brand_conf=("max_final_brand_conf", "max"),
            first_timestamp_sec=("first_timestamp_sec", "min"),
            last_timestamp_sec=("last_timestamp_sec", "max"),
        )
        .reset_index()
        .rename(columns={"business_brand": "brand"})
    )
    track_summary.to_csv(output_dir / "brand_summary_by_tracks.csv", index=False)


def write_charts(charts_dir: Path, detections_df: pd.DataFrame, tracks_df: pd.DataFrame) -> None:
    charts_dir.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    visible_detections_df = filter_business_visible(detections_df)
    visible_tracks_df = filter_business_visible(tracks_df)
    try:
        import plotly.express as px
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except Exception as exc:  # noqa: BLE001 - charts are optional artifacts
        (charts_dir / "chart_failures.txt").write_text(
            f"plotly import failed: {exc}\n",
            encoding="utf-8",
        )
        return

    def save_chart(name: str, figure) -> None:
        try:
            figure.write_image(str(charts_dir / name))
        except Exception as exc:  # noqa: BLE001 - charts are optional artifacts
            fallback_name = f"{Path(name).stem}.html"
            figure.write_html(str(charts_dir / fallback_name), include_plotlyjs="cdn")
            failures.append(f"{name}: {exc}\nfallback: {fallback_name}")

    if not visible_tracks_df.empty:
        object_brand = build_object_frame(visible_tracks_df)
        brand_summary = build_brand_chart_frame(object_brand)
        save_chart(
            "tracks_by_brand.png",
            business_bar_chart(
                px,
                brand_summary,
                x="brand_label",
                y="object_count",
                text="object_count_text",
                title="Количество рекламных объектов по брендам",
                y_title="Количество объектов",
            ),
        )
        save_chart(
            "video_visibility_by_brand.png",
            business_bar_chart(
                px,
                brand_summary,
                x="brand_label",
                y="visibility_index",
                text="visibility_index_text",
                title="Индекс заметности по брендам",
                y_title="Индекс заметности",
            ),
        )
        save_chart(
            "target_brands_count_vs_visibility.png",
            target_brands_count_vs_visibility_chart(go, make_subplots, object_brand),
        )
        save_chart(
            "visibility_share_by_brand.png",
            visibility_share_chart(px, brand_summary),
        )
        top_objects_chart = top_visible_objects_chart(px, object_brand)
        if top_objects_chart is not None:
            save_chart("top_visible_objects.png", top_objects_chart)
        timeline_chart = visibility_timeline_chart(px, visible_detections_df)
        if timeline_chart is not None:
            save_chart("visibility_timeline_by_brand.png", timeline_chart)

    if failures:
        (charts_dir / "chart_failures.txt").write_text("\n".join(failures) + "\n", encoding="utf-8")


def filter_business_visible(dataframe: pd.DataFrame) -> pd.DataFrame:
    if dataframe.empty or "business_visible" not in dataframe.columns:
        return dataframe.iloc[0:0].copy()
    visible = pd.to_numeric(dataframe["business_visible"], errors="coerce").fillna(0).astype(int) == 1
    return dataframe[visible].copy()


def build_object_frame(tracks_df: pd.DataFrame) -> pd.DataFrame:
    return (
        tracks_df.groupby(["object_id", "business_brand"], dropna=False)
        .agg(
            track_fragment_count=("track_id", "count"),
            video_visibility_weighted_seconds=("video_visibility_weighted_seconds", "sum"),
            first_timestamp_sec=("first_timestamp_sec", "min"),
            last_timestamp_sec=("last_timestamp_sec", "max"),
            mean_track_final_score=("track_final_score", "mean"),
        )
        .reset_index()
        .rename(columns={"business_brand": "brand"})
    )


def build_brand_chart_frame(object_brand: pd.DataFrame, brands: list[str] | None = None) -> pd.DataFrame:
    normalized = object_brand.copy()
    normalized["brand"] = normalize_brand_series(normalized["brand"])
    summary = (
        normalized.groupby("brand", as_index=False)
        .agg(
            object_count=("object_id", "count"),
            visibility_index=("video_visibility_weighted_seconds", "sum"),
        )
    )
    if brands is not None:
        existing = set(summary["brand"].astype(str))
        missing_rows = [
            {"brand": brand, "object_count": 0, "visibility_index": 0.0}
            for brand in brands
            if brand not in existing
        ]
        if missing_rows:
            summary = pd.concat([summary, pd.DataFrame(missing_rows)], ignore_index=True)
        summary = summary[summary["brand"].isin(brands)].copy()

    summary["brand_label"] = summary["brand"].map(brand_label)
    summary["brand_order"] = summary["brand"].map(brand_order)
    summary["object_count_text"] = summary["object_count"].map(lambda value: f"{int(value)}")
    summary["visibility_index_text"] = summary["visibility_index"].map(format_chart_number)
    return summary.sort_values(["brand_order", "brand_label"]).reset_index(drop=True)


def normalize_brand_series(series: pd.Series) -> pd.Series:
    return series.fillna("other").replace({"": "other"}).astype(str)


def brand_label(brand: str) -> str:
    return BRAND_LABELS.get(brand, brand)


def brand_order(brand: str) -> int:
    try:
        return BRAND_ORDER.index(brand)
    except ValueError:
        return len(BRAND_ORDER)


def label_color_map() -> dict[str, str]:
    return {brand_label(brand): color for brand, color in BRAND_COLORS.items()}


def ordered_labels(brands: list[str] | None = None) -> list[str]:
    if brands is None:
        brands = BRAND_ORDER
    return [brand_label(brand) for brand in brands]


def business_bar_chart(
    px: Any,
    dataframe: pd.DataFrame,
    *,
    x: str,
    y: str,
    text: str,
    title: str,
    y_title: str,
) -> Any:
    figure = px.bar(
        dataframe,
        x=x,
        y=y,
        text=text,
        color="brand_label",
        color_discrete_map=label_color_map(),
        category_orders={"brand_label": ordered_labels(), x: ordered_labels()},
        labels={x: "Бренд", y: y_title, "brand_label": "Бренд"},
        title=title,
    )
    figure.update_traces(textposition="outside", cliponaxis=False)
    apply_business_layout(figure)
    figure.update_layout(showlegend=False)
    figure.update_yaxes(title_text=y_title, rangemode="tozero")
    return figure


def target_brands_count_vs_visibility_chart(
    go: Any,
    make_subplots: Any,
    object_brand: pd.DataFrame,
) -> Any:
    dataframe = build_brand_chart_frame(object_brand, TARGET_BRANDS)
    figure = make_subplots(specs=[[{"secondary_y": True}]])
    labels = dataframe["brand_label"].tolist()

    figure.add_trace(
        go.Bar(
            x=labels,
            y=dataframe["object_count"],
            name="Количество объектов",
            marker_color="#94a3b8",
            text=dataframe["object_count_text"],
            textposition="outside",
        ),
        secondary_y=False,
    )
    figure.add_trace(
        go.Scatter(
            x=labels,
            y=dataframe["visibility_index"],
            name="Индекс заметности",
            mode="lines+markers+text",
            marker={"color": "#ffe600", "size": 10},
            line={"color": "#ffe600", "width": 3},
            text=dataframe["visibility_index_text"],
            textposition="top center",
        ),
        secondary_y=True,
    )

    figure.update_layout(title="Целевые бренды: количество и заметность")
    apply_business_layout(figure)
    figure.update_yaxes(title_text="Количество объектов", rangemode="tozero", secondary_y=False)
    figure.update_yaxes(title_text="Индекс заметности", rangemode="tozero", secondary_y=True)
    return figure


def visibility_share_chart(px: Any, brand_summary: pd.DataFrame) -> Any:
    dataframe = brand_summary[brand_summary["visibility_index"] > 0].copy()
    figure = px.pie(
        dataframe,
        names="brand_label",
        values="visibility_index",
        color="brand_label",
        color_discrete_map=label_color_map(),
        category_orders={"brand_label": ordered_labels()},
        hole=0.56,
        title="Доля заметности по брендам",
    )
    figure.update_traces(textinfo="percent+label", textposition="inside")
    apply_business_layout(figure)
    figure.update_layout(legend_title_text="")
    return figure


def top_visible_objects_chart(px: Any, object_brand: pd.DataFrame) -> Any | None:
    if object_brand.empty:
        return None

    dataframe = object_brand.copy()
    dataframe["brand"] = normalize_brand_series(dataframe["brand"])
    dataframe = dataframe.sort_values("video_visibility_weighted_seconds", ascending=False).head(10).copy()
    if dataframe.empty:
        return None

    dataframe["brand_label"] = dataframe["brand"].map(brand_label)
    dataframe["object_label"] = dataframe.apply(object_chart_label, axis=1)
    dataframe["visibility_index_text"] = dataframe["video_visibility_weighted_seconds"].map(format_chart_number)
    dataframe = dataframe.sort_values("video_visibility_weighted_seconds", ascending=True)
    figure = px.bar(
        dataframe,
        x="video_visibility_weighted_seconds",
        y="object_label",
        orientation="h",
        color="brand_label",
        text="visibility_index_text",
        color_discrete_map=label_color_map(),
        category_orders={"brand_label": ordered_labels()},
        labels={
            "video_visibility_weighted_seconds": "Индекс заметности",
            "object_label": "Объект",
            "brand_label": "Бренд",
        },
        title="Топ заметных рекламных объектов",
    )
    figure.update_traces(textposition="outside", cliponaxis=False)
    apply_business_layout(figure)
    figure.update_yaxes(title_text="")
    figure.update_xaxes(title_text="Индекс заметности", rangemode="tozero")
    return figure


def visibility_timeline_chart(px: Any, detections_df: pd.DataFrame) -> Any | None:
    if detections_df.empty:
        return None

    required_columns = {
        "timestamp_sec",
        "object_id",
        "business_brand",
        "video_visibility_score",
    }
    if not required_columns.issubset(detections_df.columns):
        return None

    dataframe = detections_df.copy()
    dataframe["brand"] = normalize_brand_series(dataframe["business_brand"])
    dataframe["timestamp_sec"] = pd.to_numeric(dataframe["timestamp_sec"], errors="coerce")
    dataframe["video_visibility_score"] = pd.to_numeric(dataframe["video_visibility_score"], errors="coerce")
    dataframe = dataframe.dropna(subset=["timestamp_sec", "video_visibility_score", "object_id"])
    if dataframe.empty:
        return None

    dataframe["time_bucket_sec"] = (
        dataframe["timestamp_sec"] // TIMELINE_BUCKET_SECONDS
    ).astype(int) * TIMELINE_BUCKET_SECONDS
    object_bucket = (
        dataframe.groupby(["time_bucket_sec", "object_id", "brand"], as_index=False)
        .agg(visibility_index=("video_visibility_score", "max"))
    )
    timeline = (
        object_bucket.groupby(["time_bucket_sec", "brand"], as_index=False)["visibility_index"]
        .sum()
    )
    if timeline.empty:
        return None
    timeline = complete_timeline_buckets(timeline)

    timeline["brand_label"] = timeline["brand"].map(brand_label)
    timeline["time_label"] = timeline["time_bucket_sec"].map(format_chart_time)
    figure = px.area(
        timeline,
        x="time_bucket_sec",
        y="visibility_index",
        color="brand_label",
        color_discrete_map=label_color_map(),
        category_orders={"brand_label": ordered_labels()},
        labels={
            "time_bucket_sec": "Время маршрута",
            "visibility_index": "Индекс заметности",
            "brand_label": "Бренд",
        },
        title="Заметность брендов по времени маршрута",
    )
    figure.update_traces(line_shape="hv")
    apply_business_layout(figure)
    figure.update_layout(
        annotations=[
            {
                "text": f"Агрегация по окнам {TIMELINE_BUCKET_SECONDS} секунд",
                "xref": "paper",
                "yref": "paper",
                "x": 0,
                "y": 1.08,
                "showarrow": False,
                "font": {"size": 13, "color": "#64748b"},
            }
        ]
    )
    figure.update_xaxes(
        title_text="Время маршрута",
        tickmode="array",
        tickvals=timeline_ticks(timeline["time_bucket_sec"]),
        ticktext=[format_chart_time(value) for value in timeline_ticks(timeline["time_bucket_sec"])],
    )
    figure.update_yaxes(title_text="Индекс заметности", rangemode="tozero")
    return figure


def complete_timeline_buckets(timeline: pd.DataFrame) -> pd.DataFrame:
    minimum = int(timeline["time_bucket_sec"].min())
    maximum = int(timeline["time_bucket_sec"].max())
    buckets = list(range(minimum, maximum + TIMELINE_BUCKET_SECONDS, TIMELINE_BUCKET_SECONDS))
    brands = [brand for brand in BRAND_ORDER if brand in set(timeline["brand"])]
    index = pd.MultiIndex.from_product([buckets, brands], names=["time_bucket_sec", "brand"])
    return (
        timeline.set_index(["time_bucket_sec", "brand"])
        .reindex(index, fill_value=0.0)
        .reset_index()
    )


def timeline_ticks(series: pd.Series) -> list[int]:
    if series.empty:
        return []
    minimum = int(series.min())
    maximum = int(series.max())
    span = max(TIMELINE_BUCKET_SECONDS, maximum - minimum)
    target_ticks = 8
    step = max(TIMELINE_BUCKET_SECONDS, round(span / target_ticks / TIMELINE_BUCKET_SECONDS) * TIMELINE_BUCKET_SECONDS)
    return list(range(minimum, maximum + step, step))


def object_chart_label(row: pd.Series) -> str:
    return f"{row['brand_label']} · {format_chart_time(row['first_timestamp_sec'])} · #{int(row['object_id'])}"


def apply_business_layout(figure: Any) -> None:
    figure.update_layout(
        template="plotly_white",
        width=1100,
        height=650,
        title_x=0.02,
        title_font={"size": 24},
        font={"family": "Arial, sans-serif", "size": 15},
        margin={"l": 80, "r": 50, "t": 90, "b": 80},
        legend_title_text="",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
    )
    figure.update_xaxes(showgrid=False)
    figure.update_yaxes(gridcolor="rgba(148, 163, 184, 0.22)")


def format_chart_number(value: Any) -> str:
    numeric_value = float(value)
    if abs(numeric_value) >= 10:
        return f"{numeric_value:.1f}"
    return f"{numeric_value:.2f}"


def format_chart_time(seconds: Any) -> str:
    total = max(0, int(float(seconds)))
    minutes = total // 60
    rest = total % 60
    return f"{minutes:02d}:{rest:02d}"


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
        parts.append(table_from_rows(visible_tracks_df[display_columns].head(50).to_dict("records")))

    parts.append("<h2>Detection Summary</h2>")
    if visible_detections_df.empty:
        parts.append("<p>No detections found.</p>")
    else:
        brand_counts = visible_detections_df["business_brand"].value_counts().reset_index()
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
        html_rows.extend(f"<td>{html.escape(str(row.get(column, '')))}</td>" for column in columns)
        html_rows.append("</tr>")
    html_rows.append("</tbody></table>")
    return "".join(html_rows)
