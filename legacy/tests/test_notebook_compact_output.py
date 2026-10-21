"""Notebook 僅保留人工快覽資訊，完整追蹤資料留在 manifest。"""

from LLM_as_a_Judge.LLM_as_a_Judge import LLMAsAJudge


def _evaluator():
    evaluator = object.__new__(LLMAsAJudge)
    evaluator._current_step1_trace = {
        "step1_enabled": True,
        "raw_response": "不應進入 notebook",
        "normalized_result": {"大量": "內容"},
        "court_metadata_passed": "full_court_place",
        "needs_court_info_source": "llm",
        "parse_error": "",
    }
    evaluator._current_template_record = {
        "lab_enabled": True,
        "contract": {"presentation": ["heatmap"]},
        "actual_route": "renderer",
        "renderer_status": "completed",
        "fallback_reason": "",
    }
    evaluator.notebook = {"cells": []}
    return evaluator


def test_notebook_routing_is_compact_and_excludes_raw_json() -> None:
    summary = _evaluator()._notebook_routing_markdown()

    assert summary.startswith("### 流程摘要")
    assert "完整場地資訊" in summary
    assert "heatmap" in summary
    assert "renderer / completed" in summary
    assert "raw_response" not in summary
    assert "不應進入 notebook" not in summary
    assert "~~~json" not in summary
    assert len(summary) < 300


def test_notebook_code_keeps_short_stdout_and_images() -> None:
    evaluator = _evaluator()
    evaluator._add_notebook_code(
        "print('結果')",
        ["image-data"],
        "重要統計：42\n",
    )

    outputs = evaluator.notebook["cells"][0]["outputs"]
    assert outputs[0]["output_type"] == "stream"
    assert outputs[0]["text"] == ["重要統計：42\n"]
    assert outputs[1]["output_type"] == "display_data"


def test_notebook_stdout_is_truncated() -> None:
    stdout = "\n".join(f"line-{index}" for index in range(30))

    compact = LLMAsAJudge._compact_notebook_stdout(stdout, max_lines=3)

    assert "line-0" in compact
    assert "line-2" in compact
    assert "line-3" not in compact
    assert "輸出已截斷" in compact
    assert "notebook 僅保留重點" in compact
    assert "summary／CSV" not in compact
