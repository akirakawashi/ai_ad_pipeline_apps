"""Business chart builders for pipeline reports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .common import (
    brand_label,
    brand_order,
    filter_business_visible,
    format_chart_number,
    format_chart_time,
    label_color_map,
    normalize_brand_series,
    ordered_labels,
)
from .constants import (
    BRAND_ORDER,
    TARGET_BRANDS,
    TIMELINE_BUCKET_SECONDS,
)


def write_charts(
    charts_dir: Path, detections_df: pd.DataFrame, tracks_df: pd.DataFrame
) -> None:
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
        (charts_dir / "chart_failures.txt").write_text(
            "\n".join(failures) + "\n", encoding="utf-8"
        )


def build_object_frame(tracks_df: pd.DataFrame) -> pd.DataFrame:
    return (
        tracks_df.groupby(["object_id", "business_brand"], dropna=False)
        .agg(
            track_fragment_count=("track_id", "count"),
            video_visibility_weighted_seconds=(
                "video_visibility_weighted_seconds",
                "sum",
            ),
            first_timestamp_sec=("first_timestamp_sec", "min"),
            last_timestamp_sec=("last_timestamp_sec", "max"),
            mean_track_final_score=("track_final_score", "mean"),
        )
        .reset_index()
        .rename(columns={"business_brand": "brand"})
    )


def build_brand_chart_frame(
    object_brand: pd.DataFrame, brands: list[str] | None = None
) -> pd.DataFrame:
    normalized = object_brand.copy()
    normalized["brand"] = normalize_brand_series(normalized["brand"])
    summary = normalized.groupby("brand", as_index=False).agg(
        object_count=("object_id", "count"),
        visibility_index=("video_visibility_weighted_seconds", "sum"),
    )
    if brands is not None:
        existing = set(summary["brand"].astype(str))
        missing_rows = [
            {"brand": brand, "object_count": 0, "visibility_index": 0.0}
            for brand in brands
            if brand not in existing
        ]
        if missing_rows:
            summary = pd.concat(
                [summary, pd.DataFrame(missing_rows)], ignore_index=True
            )
        summary = summary[summary["brand"].isin(brands)].copy()

    summary["brand_label"] = summary["brand"].map(brand_label)
    summary["brand_order"] = summary["brand"].map(brand_order)
    summary["object_count_text"] = summary["object_count"].map(
        lambda value: f"{int(value)}"
    )
    summary["visibility_index_text"] = summary["visibility_index"].map(
        format_chart_number
    )
    return summary.sort_values(["brand_order", "brand_label"]).reset_index(drop=True)


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
    figure.update_yaxes(
        title_text="Количество объектов", rangemode="tozero", secondary_y=False
    )
    figure.update_yaxes(
        title_text="Индекс заметности", rangemode="tozero", secondary_y=True
    )
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
    dataframe = (
        dataframe.sort_values("video_visibility_weighted_seconds", ascending=False)
        .head(10)
        .copy()
    )
    if dataframe.empty:
        return None

    dataframe["brand_label"] = dataframe["brand"].map(brand_label)
    dataframe["object_label"] = dataframe.apply(object_chart_label, axis=1)
    dataframe["visibility_index_text"] = dataframe[
        "video_visibility_weighted_seconds"
    ].map(format_chart_number)
    dataframe = dataframe.sort_values(
        "video_visibility_weighted_seconds", ascending=True
    )
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
    dataframe["timestamp_sec"] = pd.to_numeric(
        dataframe["timestamp_sec"], errors="coerce"
    )
    dataframe["video_visibility_score"] = pd.to_numeric(
        dataframe["video_visibility_score"], errors="coerce"
    )
    dataframe = dataframe.dropna(
        subset=["timestamp_sec", "video_visibility_score", "object_id"]
    )
    if dataframe.empty:
        return None

    dataframe["time_bucket_sec"] = (
        dataframe["timestamp_sec"] // TIMELINE_BUCKET_SECONDS
    ).astype(int) * TIMELINE_BUCKET_SECONDS
    object_bucket = dataframe.groupby(
        ["time_bucket_sec", "object_id", "brand"], as_index=False
    ).agg(visibility_index=("video_visibility_score", "max"))
    timeline = object_bucket.groupby(["time_bucket_sec", "brand"], as_index=False)[
        "visibility_index"
    ].sum()
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
        ticktext=[
            format_chart_time(value)
            for value in timeline_ticks(timeline["time_bucket_sec"])
        ],
    )
    figure.update_yaxes(title_text="Индекс заметности", rangemode="tozero")
    return figure


def complete_timeline_buckets(timeline: pd.DataFrame) -> pd.DataFrame:
    minimum = int(timeline["time_bucket_sec"].min())
    maximum = int(timeline["time_bucket_sec"].max())
    buckets = list(
        range(minimum, maximum + TIMELINE_BUCKET_SECONDS, TIMELINE_BUCKET_SECONDS)
    )
    brands = [brand for brand in BRAND_ORDER if brand in set(timeline["brand"])]
    index = pd.MultiIndex.from_product(
        [buckets, brands], names=["time_bucket_sec", "brand"]
    )
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
    step = max(
        TIMELINE_BUCKET_SECONDS,
        round(span / target_ticks / TIMELINE_BUCKET_SECONDS) * TIMELINE_BUCKET_SECONDS,
    )
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
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
        },
    )
    figure.update_xaxes(showgrid=False)
    figure.update_yaxes(gridcolor="rgba(148, 163, 184, 0.22)")
