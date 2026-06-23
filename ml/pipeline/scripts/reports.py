"""Compatibility facade for report output helpers."""

from __future__ import annotations

from .reporting.charts import (
    build_brand_chart_frame,
    build_object_frame,
    business_bar_chart,
    complete_timeline_buckets,
    target_brands_count_vs_visibility_chart,
    timeline_ticks,
    top_visible_objects_chart,
    visibility_share_chart,
    visibility_timeline_chart,
    write_charts,
)
from .reporting.common import (
    brand_label,
    brand_order,
    filter_business_visible,
    format_chart_number,
    format_chart_time,
    label_color_map,
    normalize_brand_series,
    ordered_labels,
)
from .reporting.csv_io import write_dict_csv, write_input_meta
from .reporting.html_report import table_from_rows, write_html_report
from .reporting.summaries import write_summaries
from .reporting.writer import write_pipeline_outputs

__all__ = [
    "brand_label",
    "brand_order",
    "build_brand_chart_frame",
    "build_object_frame",
    "business_bar_chart",
    "complete_timeline_buckets",
    "filter_business_visible",
    "format_chart_number",
    "format_chart_time",
    "label_color_map",
    "normalize_brand_series",
    "ordered_labels",
    "table_from_rows",
    "target_brands_count_vs_visibility_chart",
    "timeline_ticks",
    "top_visible_objects_chart",
    "visibility_share_chart",
    "visibility_timeline_chart",
    "write_charts",
    "write_dict_csv",
    "write_html_report",
    "write_input_meta",
    "write_pipeline_outputs",
    "write_summaries",
]
