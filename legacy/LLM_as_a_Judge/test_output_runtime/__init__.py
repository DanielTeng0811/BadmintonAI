"""只供 MODE=test 後續實驗使用的呈現 runtime。

Phase 4 尚未接入評估器；正式模式不得 import 本套件。
"""

from .payloads import (
    ChartSeries,
    CompositeItem,
    CompositeResult,
    HeatmapPoints,
    RecordResult,
    ScalarResult,
    TableResult,
)
from .renderers import (
    RUNTIME_VERSION,
    figure_to_png_bytes,
    render_bar,
    render_composite,
    render_heatmap,
    render_line,
    render_pie,
    render_scatter,
    render_table,
    render_text,
    save_figure,
)

__all__ = [
    "ChartSeries",
    "CompositeItem",
    "CompositeResult",
    "HeatmapPoints",
    "RecordResult",
    "ScalarResult",
    "TableResult",
    "RUNTIME_VERSION",
    "figure_to_png_bytes",
    "render_bar",
    "render_composite",
    "render_heatmap",
    "render_line",
    "render_pie",
    "render_scatter",
    "render_table",
    "render_text",
    "save_figure",
]
