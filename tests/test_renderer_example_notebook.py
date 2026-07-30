"""Phase 4 renderer 範例 notebook 的離線產生與執行測試。"""

import json

from LLM_as_a_Judge.test_output_runtime.generate_examples import (
    EXAMPLES,
    build_and_execute_notebook,
)


def test_example_notebook_executes_every_template_and_embeds_images(tmp_path) -> None:
    notebook_path = build_and_execute_notebook(
        tmp_path / "renderer_examples.ipynb"
    )
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    code_cells = [
        cell for cell in notebook["cells"]
        if cell["cell_type"] == "code"
    ]
    image_outputs = [
        output
        for cell in code_cells
        for output in cell["outputs"]
        if "image/png" in output.get("data", {})
    ]

    assert notebook["nbformat"] == 4
    assert notebook["metadata"]["renderer_runtime"]["offline_executed"] is True
    assert len(code_cells) == len(EXAMPLES) + 1
    assert all(cell["execution_count"] is not None for cell in code_cells)
    assert len(image_outputs) == 6
    assert all(len(output["data"]["image/png"]) > 1_000 for output in image_outputs)
    assert len(list((tmp_path / "images").glob("*.png"))) == 6


def test_notebook_contains_real_runtime_calls_and_all_required_examples(tmp_path) -> None:
    notebook_path = build_and_execute_notebook(tmp_path / "examples.ipynb")
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    source = "\n".join(
        "".join(cell["source"])
        for cell in notebook["cells"]
    )

    for renderer in (
        "render_text",
        "render_table",
        "render_bar",
        "render_pie",
        "render_line",
        "render_scatter",
        "render_heatmap",
        "render_composite",
    ):
        assert f"{renderer}(" in source
    assert "LLM_as_a_Judge.test_output_runtime" in source
