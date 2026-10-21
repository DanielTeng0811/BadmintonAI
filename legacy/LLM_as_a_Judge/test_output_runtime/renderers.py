"""固定樣式、無領域邏輯的 test-only renderer。"""

from io import BytesIO
from pathlib import Path
import re
from typing import Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .payloads import (
    MAX_BAR_SERIES,
    MAX_ROWS,
    MAX_SERIES,
    ChartSeries,
    CompositeResult,
    HeatmapPoints,
    RecordResult,
    ScalarResult,
    TableResult,
)


RUNTIME_VERSION = "phase6.2-v3"
_COLORS = (
    "#3568A8", "#E07A3F", "#4B9B69", "#8A5FBF", "#D4A72C", "#5C879B",
    "#C44E52", "#8172B3", "#CCB974", "#64B5CD", "#937860", "#55A868",
)
_SAFE_ARTIFACT_NAME = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
_MAX_VISIBLE_COMPOSITE_TABLE_ROWS = 30
_TABLE_TITLE_RESERVED_FRACTION = 0.10

# 字體設定集中在 renderer；生成程式不需要重複輸出 rcParams。
plt.rcParams["font.sans-serif"] = [
    "Microsoft JhengHei",
    "Microsoft YaHei",
    "DejaVu Sans",
]
plt.rcParams["axes.unicode_minus"] = False


def _new_figure(title="", figsize=(9, 5)):
    fig, ax = plt.subplots(figsize=figsize)
    if title:
        ax.set_title(title)
    return fig, ax


def _empty_axis(ax, message="無資料"):
    ax.clear()
    ax.axis("off")
    ax.text(0.5, 0.5, message, ha="center", va="center", color="#666666")


def _as_series_list(
    series,
    max_series=MAX_SERIES,
    chart_name="圖表",
) -> tuple[ChartSeries, ...]:
    if isinstance(series, ChartSeries):
        values = (series,)
    elif isinstance(series, Sequence) and not isinstance(series, (str, bytes)):
        values = tuple(series)
    else:
        raise TypeError("series 必須是 ChartSeries 或其序列")
    if not values:
        return ()
    if len(values) > max_series:
        raise ValueError(f"{chart_name} 最多 {max_series} 個 series")
    if any(not isinstance(item, ChartSeries) for item in values):
        raise TypeError("series 只能包含 ChartSeries")
    return values


def _shared_labels(series: tuple[ChartSeries, ...]) -> tuple[str, ...]:
    if not series:
        return ()
    labels = series[0].labels
    if any(item.labels != labels for item in series[1:]):
        raise ValueError("多序列圖表必須共用相同 labels")
    return labels


def _safe_dataframe_cell(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, np.generic):
        value = value.item()
    if type(value) in {str, int, float, bool}:
        return value
    raise TypeError("DataFrame 只能包含 scalar cell")


def _to_table_payload(payload) -> TableResult:
    if isinstance(payload, TableResult):
        return payload
    if isinstance(payload, RecordResult):
        rows = [tuple(record.get(column) for column in payload.columns)
                for record in payload.records]
        return TableResult(payload.columns, rows, payload.title)
    if isinstance(payload, pd.DataFrame):
        if len(payload) > MAX_ROWS:
            raise ValueError(f"DataFrame 最多 {MAX_ROWS} 列")
        columns = tuple(str(column) for column in payload.columns)
        rows = [
            tuple(_safe_dataframe_cell(value) for value in row)
            for row in payload.itertuples(index=False, name=None)
        ]
        return TableResult(columns, rows)
    raise TypeError("table payload 必須是 TableResult、RecordResult 或 DataFrame")


def render_text(payload) -> str:
    """將純量、records、table、DataFrame 或 scalar 清單轉成文字。"""

    if isinstance(payload, ScalarResult):
        value = "無資料" if payload.value is None else str(payload.value)
        result = f"{payload.label}: {value}{payload.unit}"
        return f"{result}\n{payload.note}" if payload.note else result
    if isinstance(payload, (RecordResult, TableResult, pd.DataFrame)):
        table = render_table(payload)
        if table.empty:
            return "無資料"
        return table.to_string(index=False)
    if isinstance(payload, str):
        if len(payload) > 5_000:
            raise ValueError("text 超過長度上限 5000")
        return payload or "無資料"
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes)):
        values = tuple(payload)
        if len(values) > MAX_ROWS:
            raise ValueError(f"清單最多 {MAX_ROWS} 筆")
        if any(type(value) not in {str, int, float, bool} for value in values):
            raise TypeError("文字清單只能包含 scalar")
        return "\n".join(f"- {value}" for value in values) or "無資料"
    raise TypeError("不支援的 text payload")


def render_table(payload) -> pd.DataFrame:
    """回傳欄位順序固定的 DataFrame，不修改輸入物件。"""

    table = _to_table_payload(payload)
    return pd.DataFrame(list(table.rows), columns=list(table.columns))


def _draw_bar(ax, series):
    series = _as_series_list(
        series,
        max_series=MAX_BAR_SERIES,
        chart_name="bar",
    )
    labels = _shared_labels(series)
    if not series or not labels:
        _empty_axis(ax)
        return
    positions = np.arange(len(labels))
    width = 0.8 / len(series)
    for index, item in enumerate(series):
        offset = (index - (len(series) - 1) / 2) * width
        ax.bar(
            positions + offset,
            item.values,
            width,
            label=item.name,
            color=_COLORS[index],
        )
    ax.axhline(0, color="#777777", linewidth=0.8)
    ax.set_xticks(positions, labels)
    if max(map(len, labels), default=0) > 12 or len(labels) > 8:
        ax.tick_params(axis="x", labelrotation=35)
    if len(series) > 1:
        ax.legend()
    ax.grid(axis="y", alpha=0.2)


def render_bar(series, title=""):
    fig, ax = _new_figure(title)
    _draw_bar(ax, series)
    fig.tight_layout()
    return fig


def _draw_pie(ax, series):
    series = _as_series_list(series)
    if len(series) > 1:
        raise ValueError("pie 只能使用一個 series")
    if not series or not series[0].values:
        _empty_axis(ax)
        return
    item = series[0]
    if any(value < 0 for value in item.values):
        raise ValueError("pie 不接受負值")
    if sum(item.values) <= 0:
        _empty_axis(ax, "無可繪製的正值資料")
        return
    ax.pie(
        item.values,
        labels=item.labels,
        autopct="%1.1f%%",
        colors=_COLORS[:len(item.values)],
        startangle=90,
    )
    ax.axis("equal")


def render_pie(series, title=""):
    fig, ax = _new_figure(title, figsize=(7, 6))
    _draw_pie(ax, series)
    fig.tight_layout()
    return fig


def _draw_line(ax, series):
    series = _as_series_list(series, chart_name="line")
    labels = _shared_labels(series)
    if not series or not labels:
        _empty_axis(ax)
        return
    positions = np.arange(len(labels))
    for index, item in enumerate(series):
        ax.plot(
            positions,
            item.values,
            marker="o",
            linewidth=2,
            label=item.name,
            color=_COLORS[index],
        )
    ax.set_xticks(positions, labels)
    if len(series) > 1:
        if len(series) > 6:
            ax.legend(fontsize=8, ncol=2)
        else:
            ax.legend()
    ax.grid(alpha=0.25)


def render_line(series, title=""):
    fig, ax = _new_figure(title)
    _draw_line(ax, series)
    fig.tight_layout()
    return fig


def _draw_scatter(ax, series):
    series = _as_series_list(series, chart_name="scatter")
    if not series or all(not item.values for item in series):
        _empty_axis(ax)
        return
    for index, item in enumerate(series):
        try:
            x_values = tuple(float(label) for label in item.labels)
        except ValueError as error:
            raise ValueError("scatter labels 必須可轉成數值") from error
        ax.scatter(
            x_values,
            item.values,
            label=item.name,
            alpha=0.75,
            color=_COLORS[index],
        )
    if len(series) > 1:
        if len(series) > 6:
            ax.legend(fontsize=8, ncol=2)
        else:
            ax.legend()
    ax.grid(alpha=0.2)


def render_scatter(series, title=""):
    fig, ax = _new_figure(title)
    _draw_scatter(ax, series)
    fig.tight_layout()
    return fig


def _draw_heatmap(ax, points, add_colorbar=False):
    if not isinstance(points, HeatmapPoints):
        raise TypeError("heatmap payload 必須是 HeatmapPoints")
    if not points.x:
        _empty_axis(ax)
        return
    result = ax.hist2d(
        points.x,
        points.y,
        bins=20,
        weights=points.weights,
        cmap="YlOrRd",
    )
    if add_colorbar:
        ax.figure.colorbar(result[3], ax=ax, label="密度")


def render_heatmap(points, title=""):
    fig, ax = _new_figure(title, figsize=(7, 6))
    _draw_heatmap(ax, points, add_colorbar=True)
    fig.tight_layout()
    return fig


def _draw_table(ax, payload):
    table = render_table(payload)
    ax.axis("off")
    if table.empty:
        ax.text(0.5, 0.5, "無資料", ha="center", va="center")
        return
    display_table = table.head(_MAX_VISIBLE_COMPOSITE_TABLE_ROWS)
    artist = ax.table(
        cellText=display_table.values,
        colLabels=display_table.columns,
        cellLoc="center",
        # 限制在 axes 內並保留標題空間，避免多面板輸出互相覆蓋。
        bbox=(0, 0, 1, 1 - _TABLE_TITLE_RESERVED_FRACTION),
    )
    artist.auto_set_font_size(False)
    artist.set_fontsize(9)


def _composite_panel_height(item) -> float:
    """依內容估算面板高度；只處理版面，不改變資料或呈現選擇。"""

    if item.kind == "table":
        visible_rows = min(
            len(render_table(item.payload)),
            _MAX_VISIBLE_COMPOSITE_TABLE_ROWS,
        )
        # 標題、欄名與每一資料列都需要垂直空間。
        return min(10.5, max(4.0, 1.4 + 0.29 * (visible_rows + 1)))
    if item.kind == "text":
        return 3.0
    return 5.0


def render_composite(result: CompositeResult):
    """將最多四個受限 payload 畫成垂直多面板。"""

    if not isinstance(result, CompositeResult):
        raise TypeError("composite payload 必須是 CompositeResult")
    panel_heights = [_composite_panel_height(item) for item in result.items]
    fig, axes = plt.subplots(
        len(result.items),
        1,
        figsize=(12, sum(panel_heights)),
        squeeze=False,
        gridspec_kw={"height_ratios": panel_heights},
    )
    for ax, item in zip(axes.flat, result.items):
        if item.title:
            ax.set_title(item.title)
        if item.kind == "text":
            ax.axis("off")
            ax.text(0.02, 0.9, render_text(item.payload), va="top", wrap=True)
        elif item.kind == "table":
            _draw_table(ax, item.payload)
        elif item.kind == "bar":
            _draw_bar(ax, item.payload)
        elif item.kind == "pie":
            _draw_pie(ax, item.payload)
        elif item.kind == "line":
            _draw_line(ax, item.payload)
        elif item.kind == "scatter":
            _draw_scatter(ax, item.payload)
        elif item.kind == "heatmap":
            _draw_heatmap(ax, item.payload)
    fig.tight_layout(pad=2.0, h_pad=2.5)
    return fig


def figure_to_png_bytes(fig, dpi=140) -> bytes:
    """將 Figure 轉為 PNG；dpi 使用受限整數範圍。"""

    if fig is None or not hasattr(fig, "savefig"):
        raise TypeError("fig 必須是 Matplotlib Figure")
    if type(dpi) is not int or not 72 <= dpi <= 300:
        raise ValueError("dpi 必須是 72 到 300 的整數")
    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=dpi, bbox_inches="tight")
    return buffer.getvalue()


def save_figure(fig, output_dir, artifact_name, dpi=140) -> Path:
    """由可信任呼叫端指定目錄；payload 無法注入檔名或路徑。"""

    if not isinstance(artifact_name, str) or not _SAFE_ARTIFACT_NAME.fullmatch(
        artifact_name
    ):
        raise ValueError("artifact_name 只能使用英數、底線與連字號")
    directory = Path(output_dir).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{artifact_name}.png"
    path.write_bytes(figure_to_png_bytes(fig, dpi=dpi))
    return path
