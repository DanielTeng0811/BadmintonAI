"""Phase 4 test-only payload 與 renderer 的純離線測試。"""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import pytest

from LLM_as_a_Judge.test_output_runtime import (
    ChartSeries,
    CompositeItem,
    CompositeResult,
    HeatmapPoints,
    RecordResult,
    ScalarResult,
    TableResult,
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


@pytest.fixture(autouse=True)
def _close_figures():
    plt.close("all")
    yield
    plt.close("all")


def _assert_png(fig) -> None:
    png = figure_to_png_bytes(fig)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(png) > 1_000


def test_scalar_list_dataframe_and_empty_text_outputs() -> None:
    assert render_text(ScalarResult("成功率", 42.5, "%")) == "成功率: 42.5%"
    assert render_text(["甲", "乙"]) == "- 甲\n- 乙"
    assert "欄位" in render_text(pd.DataFrame({"欄位": [1]}))
    assert render_text([]) == "無資料"
    assert render_text(ScalarResult("結果", None)) == "結果: 無資料"


def test_record_table_dataframe_and_empty_table_are_supported() -> None:
    records = RecordResult(
        [{"類別": "甲", "值": 3}, {"類別": "乙", "值": 4}],
        columns=["類別", "值"],
    )
    table = render_table(records)
    assert list(table.columns) == ["類別", "值"]
    assert table.to_dict("records") == list(records.records)

    empty = render_table(TableResult(["類別", "值"], []))
    assert empty.empty
    assert list(empty.columns) == ["類別", "值"]


def test_payloads_reject_nested_values_and_inconsistent_shapes() -> None:
    with pytest.raises(TypeError, match="JSON scalar"):
        RecordResult([{"nested": {"bad": True}}])
    with pytest.raises(ValueError, match="長度"):
        TableResult(["A", "B"], [[1]])
    with pytest.raises(ValueError, match="長度"):
        ChartSeries("A", ["一"], [1, 2])
    with pytest.raises(TypeError, match="scalar"):
        ChartSeries("A", [{"nested": True}], [1])
    with pytest.raises(ValueError, match="最多 4"):
        CompositeResult([
            CompositeItem("text", "x") for _ in range(5)
        ])


def test_bar_handles_negative_values_long_labels_and_multi_series() -> None:
    labels = ["這是一個很長的分類標籤一", "這是一個很長的分類標籤二"]
    series = [
        ChartSeries("本期", labels, [8, -3]),
        ChartSeries("前期", labels, [5, 2]),
    ]
    fig = render_bar(series, "中文長標籤與負值")
    _assert_png(fig)
    assert len(fig.axes[0].patches) == 4


def test_bar_rejects_more_than_six_series() -> None:
    series = [
        ChartSeries(f"系列{index}", ["甲"], [index])
        for index in range(7)
    ]

    with pytest.raises(ValueError, match="bar 最多 6"):
        render_bar(series)


def test_pie_supports_single_category_and_rejects_negative_values() -> None:
    fig = render_pie(ChartSeries("比例", ["唯一類別"], [100]), "單類別")
    _assert_png(fig)

    with pytest.raises(ValueError, match="負值"):
        render_pie(ChartSeries("錯誤", ["甲", "乙"], [1, -1]))

    with pytest.raises(ValueError, match="只能使用一個"):
        render_pie([
            ChartSeries("甲", ["A"], [1]),
            ChartSeries("乙", ["A"], [2]),
        ])


def test_line_and_scatter_support_multiple_series() -> None:
    line_series = [
        ChartSeries("甲", ["一", "二", "三"], [1, 3, 2]),
        ChartSeries("乙", ["一", "二", "三"], [2, 2, 4]),
    ]
    _assert_png(render_line(line_series, "趨勢"))

    scatter_series = [
        ChartSeries("群組甲", [1, 2, 3], [3, 1, 4]),
        ChartSeries("群組乙", [1.5, 2.5, 3.5], [2, 4, 3]),
    ]
    _assert_png(render_scatter(scatter_series, "關聯"))


def test_line_supports_ten_series_without_fallback_limit() -> None:
    series = [
        ChartSeries(
            f"系列{index}",
            ["階段一", "階段二", "階段三"],
            [index, index + 1, index + 2],
        )
        for index in range(10)
    ]

    fig = render_line(series, "十序列趨勢")

    _assert_png(fig)
    assert len(fig.axes[0].lines) == 10


def test_scatter_treats_labels_as_x_and_values_as_y() -> None:
    fig = render_scatter(
        ChartSeries("站點", [-0.3, 0.1, 0.4], [0.2, -0.1, 0.6]),
        "二維散點",
    )

    offsets = fig.axes[0].collections[0].get_offsets().tolist()
    assert offsets == [[-0.3, 0.2], [0.1, -0.1], [0.4, 0.6]]


def test_chart_contract_rejects_incompatible_axes() -> None:
    with pytest.raises(ValueError, match="共用相同 labels"):
        render_line([
            ChartSeries("甲", ["一", "二"], [1, 2]),
            ChartSeries("乙", ["一", "三"], [3, 4]),
        ])

    with pytest.raises(ValueError, match="scatter labels"):
        render_scatter(ChartSeries("錯誤", ["左", "右"], [1, 2]))

    with pytest.raises(ValueError, match="長度"):
        HeatmapPoints([0.1], [0.2, 0.3])

    with pytest.raises(ValueError, match="不可為負值"):
        HeatmapPoints([0.1], [0.2], weights=[-1])


def test_heatmap_supports_points_weights_and_empty_data() -> None:
    points = HeatmapPoints(
        x=[0, 0.2, 0.8, 1.0],
        y=[0, 0.3, 0.7, 1.0],
        weights=[1, 2, 1, 3],
    )
    _assert_png(render_heatmap(points, "熱區"))
    _assert_png(render_heatmap(HeatmapPoints([], []), "空熱區"))


@pytest.mark.parametrize(
    "renderer,payload",
    [
        (render_bar, ChartSeries("空", [], [])),
        (render_pie, ChartSeries("空", [], [])),
        (render_line, ChartSeries("空", [], [])),
        (render_scatter, ChartSeries("空", [], [])),
    ],
)
def test_empty_chart_series_produce_visible_placeholder(renderer, payload) -> None:
    fig = renderer(payload)
    _assert_png(fig)
    assert fig.axes[0].texts[0].get_text() == "無資料"


def test_composite_renders_text_table_and_chart_panels() -> None:
    result = CompositeResult([
        CompositeItem("text", ScalarResult("總數", 12), "摘要"),
        CompositeItem(
            "table",
            TableResult(["類別", "值"], [["甲", 7], ["乙", 5]]),
            "明細",
        ),
        CompositeItem(
            "bar",
            ChartSeries("次數", ["甲", "乙"], [7, 5]),
            "分布",
        ),
    ])
    fig = render_composite(result)
    _assert_png(fig)
    assert len(fig.axes) == 3


def test_composite_large_table_reserves_title_space_and_panel_height() -> None:
    rows = [[f"階段 {index // 10 + 1}", f"球種 {index}", index]
            for index in range(30)]
    result = CompositeResult([
        CompositeItem(
            "table",
            TableResult(["比分階段", "球種", "頻率"], rows),
            "不同比分階段的球種使用頻率",
        ),
        CompositeItem(
            "line",
            ChartSeries("頻率", ["開局", "中局", "關鍵分"], [8, 10, 12]),
            "球種頻率變化趨勢",
        ),
    ])

    fig = render_composite(result)
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    table_ax, line_ax = fig.axes
    table_bbox = table_ax.tables[0].get_window_extent(renderer)
    table_title_bbox = table_ax.title.get_window_extent(renderer)
    line_title_bbox = line_ax.title.get_window_extent(renderer)

    assert not table_bbox.overlaps(table_title_bbox)
    assert not table_bbox.overlaps(line_title_bbox)
    assert len(table_ax.tables[0].get_celld()) == 31 * 3
    assert fig.get_figheight() > 12


def test_same_payload_produces_stable_png_in_same_environment() -> None:
    payload = ChartSeries("值", ["甲", "乙"], [1, 2])
    first = figure_to_png_bytes(render_bar(payload, "穩定輸出"))
    plt.close("all")
    second = figure_to_png_bytes(render_bar(payload, "穩定輸出"))
    assert first == second


def test_save_figure_restricts_artifact_name(tmp_path) -> None:
    fig = render_bar(ChartSeries("值", ["甲"], [1]))
    saved = save_figure(fig, tmp_path, "safe_name")
    assert saved == tmp_path.resolve() / "safe_name.png"
    assert saved.exists()

    with pytest.raises(ValueError, match="artifact_name"):
        save_figure(fig, tmp_path, "../escape")


def test_production_modules_do_not_import_test_runtime() -> None:
    root = Path(__file__).parents[1]
    protected = [
        root / "LLM_as_a_Judge" / "LLM_as_a_Judge.py",
        root / "utils" / "analysis_workflow.py",
        root / "config" / "prompts.py",
    ]
    for path in protected:
        assert "test_output_runtime" not in path.read_text(encoding="utf-8")
