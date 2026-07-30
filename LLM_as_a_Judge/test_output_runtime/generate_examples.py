"""離線產生並逐格執行 renderer 樣式範例 notebook。"""

import ast
import base64
from contextlib import redirect_stdout
from datetime import datetime, timezone
from io import StringIO
import json
from pathlib import Path
import sys

import matplotlib.figure
import matplotlib.pyplot as plt
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from LLM_as_a_Judge.test_output_runtime import (  # noqa: E402
    RUNTIME_VERSION,
    figure_to_png_bytes,
    save_figure,
)


DEFAULT_ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
DEFAULT_NOTEBOOK = DEFAULT_ARTIFACT_DIR / "renderer_examples.ipynb"

SETUP_CODE = """from pathlib import Path
import sys

PROJECT_ROOT = Path.cwd().resolve()
while PROJECT_ROOT != PROJECT_ROOT.parent and not (PROJECT_ROOT / "LLM_as_a_Judge").exists():
    PROJECT_ROOT = PROJECT_ROOT.parent
if not (PROJECT_ROOT / "LLM_as_a_Judge").exists():
    raise RuntimeError("找不到 BadmintonAI 專案根目錄")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from LLM_as_a_Judge.test_output_runtime import (
    RUNTIME_VERSION,
    ChartSeries,
    CompositeItem,
    CompositeResult,
    HeatmapPoints,
    ScalarResult,
    TableResult,
    render_bar,
    render_composite,
    render_heatmap,
    render_line,
    render_pie,
    render_scatter,
    render_table,
    render_text,
)

print(f"Renderer version: {RUNTIME_VERSION}")"""

EXAMPLES = (
    (
        "Text／Scalar",
        "適合單一數值、單位與簡短註記；不強迫產生表格或圖表。",
        """text_payload = ScalarResult(
    label="完成率",
    value=87.5,
    unit="%",
    note="固定離線示例",
)
render_text(text_payload)""",
    ),
    (
        "Table",
        "適合規則欄位與多列比較；輸出為可繼續處理的 DataFrame。",
        """table_payload = TableResult(
    columns=["類別", "數量", "比例"],
    rows=[
        ["類別甲", 18, 45.0],
        ["類別乙", 14, 35.0],
        ["類別丙", 8, 20.0],
    ],
    title="類別摘要",
)
render_table(table_payload)""",
    ),
    (
        "Bar",
        "適合分類比較；示例包含多序列與負值。",
        """bar_payload = [
    ChartSeries("本期", ["類別甲", "類別乙", "類別丙"], [18, 14, -3]),
    ChartSeries("前期", ["類別甲", "類別乙", "類別丙"], [15, 11, 4]),
]
render_bar(bar_payload, title="分類比較")""",
    ),
    (
        "Pie",
        "適合非負、總和大於零的組成比例。",
        """pie_payload = ChartSeries(
    "比例",
    ["類別甲", "類別乙", "類別丙"],
    [45, 35, 20],
)
render_pie(pie_payload, title="組成比例")""",
    ),
    (
        "Line",
        "適合有順序的階段或時間趨勢，支援多序列。",
        """line_payload = [
    ChartSeries("指標甲", ["階段一", "階段二", "階段三"], [12, 18, 16]),
    ChartSeries("指標乙", ["階段一", "階段二", "階段三"], [9, 13, 20]),
]
render_line(line_payload, title="階段趨勢")""",
    ),
    (
        "Scatter",
        "適合兩個連續變數的關聯；labels 作為 X 值。",
        """scatter_payload = [
    ChartSeries("群組甲", [1, 2, 3, 4], [2.0, 2.8, 3.1, 4.2]),
    ChartSeries("群組乙", [1.5, 2.5, 3.5], [3.0, 2.2, 4.0]),
]
render_scatter(scatter_payload, title="變數關聯")""",
    ),
    (
        "Heatmap",
        "適合二維連續點的密度或權重分布。",
        """heatmap_payload = HeatmapPoints(
    x=[0.1, 0.2, 0.25, 0.7, 0.75, 0.8, 0.85, 0.9],
    y=[0.2, 0.25, 0.3, 0.65, 0.7, 0.72, 0.8, 0.85],
    weights=[1, 2, 1, 1, 3, 2, 2, 1],
)
render_heatmap(heatmap_payload, title="二維熱區")""",
    ),
    (
        "Composite",
        "適合有限的文字、表格與圖表組合；最多四個面板。",
        """composite_payload = CompositeResult([
    CompositeItem("text", ScalarResult("總數", 40), title="摘要"),
    CompositeItem("table", table_payload, title="明細"),
    CompositeItem("bar", ChartSeries("數量", ["甲", "乙", "丙"], [18, 14, 8]), title="分布"),
])
render_composite(composite_payload)""",
    ),
)


def _markdown_cell(source):
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": source.splitlines(keepends=True),
    }


def _code_cell(source, execution_count, outputs):
    return {
        "cell_type": "code",
        "execution_count": execution_count,
        "metadata": {},
        "outputs": outputs,
        "source": source.splitlines(keepends=True),
    }


def _execute_source(source, namespace):
    """以乾淨 namespace 執行 code cell，並回傳最後一個 expression。"""

    module = ast.parse(source, mode="exec")
    result = None
    stdout = StringIO()
    with redirect_stdout(stdout):
        if module.body and isinstance(module.body[-1], ast.Expr):
            expression = ast.Expression(module.body.pop().value)
            if module.body:
                exec(compile(module, "<renderer-example>", "exec"), namespace)
            result = eval(
                compile(expression, "<renderer-example>", "eval"),
                namespace,
            )
        else:
            exec(compile(module, "<renderer-example>", "exec"), namespace)
    return result, stdout.getvalue()


def _serialize_outputs(result, stdout, image_dir, artifact_name):
    outputs = []
    if stdout:
        outputs.append({
            "name": "stdout",
            "output_type": "stream",
            "text": stdout.splitlines(keepends=True),
        })
    if isinstance(result, matplotlib.figure.Figure):
        png = figure_to_png_bytes(result)
        save_figure(result, image_dir, artifact_name)
        outputs.append({
            "data": {
                "image/png": base64.b64encode(png).decode("ascii"),
                "text/plain": [f"<Figure {artifact_name}>"],
            },
            "execution_count": None,
            "metadata": {},
            "output_type": "execute_result",
        })
        plt.close(result)
    elif isinstance(result, pd.DataFrame):
        outputs.append({
            "data": {
                "text/html": [result.to_html(index=False)],
                "text/plain": result.to_string(index=False).splitlines(keepends=True),
            },
            "execution_count": None,
            "metadata": {},
            "output_type": "execute_result",
        })
    elif result is not None:
        outputs.append({
            "data": {"text/plain": [repr(result)]},
            "execution_count": None,
            "metadata": {},
            "output_type": "execute_result",
        })
    return outputs


def build_and_execute_notebook(notebook_path=DEFAULT_NOTEBOOK):
    """重建 notebook 與圖片；任一 cell 失敗就不產生成功結果。"""

    notebook_path = Path(notebook_path).resolve()
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    image_dir = notebook_path.parent / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    namespace = {"__name__": "__renderer_notebook__"}
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cells = [
        _markdown_cell(
            "# Test-only Renderer 樣式範例\n\n"
            f"Runtime：`{RUNTIME_VERSION}`  \n"
            f"產生時間（UTC）：`{generated_at}`  \n"
            "所有 payload 都是固定、領域無關的離線資料。"
        )
    ]

    execution_count = 1
    setup_result, setup_stdout = _execute_source(SETUP_CODE, namespace)
    cells.append(_code_cell(
        SETUP_CODE,
        execution_count,
        _serialize_outputs(
            setup_result,
            setup_stdout,
            image_dir,
            "setup",
        ),
    ))

    for index, (name, description, source) in enumerate(EXAMPLES, start=1):
        execution_count += 1
        cells.append(_markdown_cell(f"## {name}\n\n{description}"))
        result, stdout = _execute_source(source, namespace)
        outputs = _serialize_outputs(
            result,
            stdout,
            image_dir,
            f"{index:02d}_{name.lower().replace('／', '_')}",
        )
        for output in outputs:
            if output.get("output_type") == "execute_result":
                output["execution_count"] = execution_count
        cells.append(_code_cell(source, execution_count, outputs))

    notebook = {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": sys.version.split()[0]},
            "renderer_runtime": {
                "version": RUNTIME_VERSION,
                "generated_at_utc": generated_at,
                "offline_executed": True,
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    notebook_path.write_text(
        json.dumps(notebook, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    return notebook_path


if __name__ == "__main__":
    path = build_and_execute_notebook()
    print(f"已產生並離線執行：{path}")
