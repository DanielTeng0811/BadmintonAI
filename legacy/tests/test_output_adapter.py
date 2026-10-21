"""Phase 5 test-only adapter 的純離線測試。"""

import matplotlib.pyplot as plt

from LLM_as_a_Judge.test_output_adapter import (
    estimate_code_token_split,
    estimate_prompt_token_split,
    finalize_template_report,
    prepare_template_execution,
)


def _enhancement(contract, status="valid", route="renderer_candidate"):
    return {
        "normalized_result": {"output_contract": contract},
        "output_contract_status": status,
        "output_contract_route": route,
    }


def test_valid_contract_adds_concise_prompt_and_only_safe_facade() -> None:
    contract = {
        "answer_shape": "records",
        "presentation": ["bar"],
        "explicitly_requested": True,
        "confidence": "high",
    }
    context = prepare_template_execution("BASE", _enhancement(contract))

    assert context.system_prompt.startswith("BASE")
    assert "render_output(kind, payload" in context.system_prompt
    assert "不改變分析邏輯" in context.system_prompt
    assert "先建立題意指定的完整母體再定義事件分子" in context.system_prompt
    assert "不可先用結果欄位縮小分母" in context.system_prompt
    assert "主動得分限擊球／球種直接得分" in context.system_prompt
    assert "回合情境得分依最終 getpoint_player" in context.system_prompt
    assert "不限最後擊球者" in context.system_prompt
    assert "先彙整成每個目標單位一列再計數" in context.system_prompt
    assert "不可把群組結果在原始列上重複加總" in context.system_prompt
    assert "取代上方關於自行繪圖" in context.system_prompt
    assert "Step 2 只輸出可驗證" in context.system_prompt
    assert "交由 Step 4" in context.system_prompt
    assert "Q80" not in context.system_prompt
    assert "Q54" not in context.system_prompt
    assert "掛網" not in context.system_prompt
    assert "一拍得分" not in context.system_prompt
    assert "CHOU Tien Chen" not in context.system_prompt
    assert "bar={" in context.system_prompt
    assert "heatmap={" not in context.system_prompt
    assert set(context.extended_globals) == {"render_output"}
    assert context.report["planned_route"] == "renderer_candidate"
    assert context.report["requires_insight"] is False


def test_score_semantics_cover_direct_stroke_and_rally_winner_without_retry() -> None:
    contract = {
        "answer_shape": "scalar",
        "presentation": ["text"],
        "confidence": "high",
    }
    context = prepare_template_execution("BASE", _enhancement(contract))

    # 同一條規則必須同時保留兩個語意分支，不能把所有得分都縮成主動得分。
    assert "主動得分限擊球／球種直接得分" in context.system_prompt
    assert "回合情境得分依最終 getpoint_player" in context.system_prompt
    assert context.report["renderer_calls"] == 0
    assert context.report["planned_route"] == "renderer_candidate"


def test_chart_prompt_explains_each_runtime_contract_concisely() -> None:
    cases = {
        "bar": ("最多6個series", "共用labels"),
        "pie": ("只能1個series", "非負數值"),
        "line": ("最多12個series", "共用labels"),
        "scatter": ("labels\": X數值", "X/Y等長"),
        "heatmap": ('heatmap={"x": X數值, "y": Y數值', "三者等長"),
    }

    for presentation, expected in cases.items():
        contract = {
            "answer_shape": "records",
            "presentation": [presentation],
            "confidence": "high",
        }
        prompt = prepare_template_execution(
            "BASE",
            _enhancement(contract),
        ).system_prompt
        assert all(value in prompt for value in expected)
        assert "Q19" not in prompt
        assert "Q22" not in prompt

    assert len(prepare_template_execution(
        "BASE",
        _enhancement({
            "answer_shape": "records",
            "presentation": ["scatter"],
            "confidence": "high",
        }),
    ).system_prompt) < 1_000


def test_scatter_xy_payload_uses_labels_for_x_and_values_for_y() -> None:
    contract = {
        "answer_shape": "records",
        "presentation": ["scatter"],
        "confidence": "high",
    }
    context = prepare_template_execution("BASE", _enhancement(contract))

    result = context.extended_globals["render_output"](
        "scatter",
        {
            "series": [{
                "name": "站點",
                "labels": [-0.3, 0.1, 0.4],
                "values": [0.2, -0.1, 0.6],
            }]
        },
    )

    assert hasattr(result, "savefig")
    assert context.report["renderer_status"] == "completed"
    assert context.report["artifact_nonempty"] is True
    plt.close("all")


def test_composite_table_and_ten_series_line_render_without_fallback() -> None:
    contract = {
        "answer_shape": "composite",
        "presentation": ["table", "line"],
        "confidence": "high",
    }
    context = prepare_template_execution("BASE", _enhancement(contract))
    line_series = [
        {
            "name": f"系列{index}",
            "labels": ["階段一", "階段二", "階段三"],
            "values": [index, index + 1, index + 2],
        }
        for index in range(10)
    ]

    result = context.extended_globals["render_output"](
        "composite",
        {
            "items": [
                {
                    "kind": "table",
                    "payload": {"columns": ["類別", "值"], "rows": [["甲", 1]]},
                },
                {
                    "kind": "line",
                    "payload": {"series": line_series},
                },
            ]
        },
    )

    assert hasattr(result, "savefig")
    assert context.report["actual_route"] == "renderer"
    assert context.report["fallback_reason"] == ""
    assert context.report["artifact_nonempty"] is True
    plt.close("all")


def test_low_confidence_keeps_existing_prompt_and_free_code_route() -> None:
    contract = {
        "answer_shape": "narrative",
        "presentation": ["text"],
        "explicitly_requested": False,
        "confidence": "low",
    }
    context = prepare_template_execution(
        "UNCHANGED",
        _enhancement(contract, route="existing_free_code"),
    )

    assert context.system_prompt == "UNCHANGED"
    assert context.extended_globals == {}
    assert context.report["enabled"] is False
    assert context.report["actual_route"] == "existing_free_code"


def test_renderer_success_uses_dict_payload_and_creates_figure() -> None:
    contract = {
        "answer_shape": "records",
        "presentation": ["bar"],
        "explicitly_requested": True,
        "confidence": "high",
    }
    context = prepare_template_execution("BASE", _enhancement(contract))
    result = context.extended_globals["render_output"](
        "bar",
        {
            "series": [{
                "name": "數量",
                "labels": ["甲", "乙"],
                "values": [3, 5],
            }]
        },
        "分布",
    )

    assert hasattr(result, "savefig")
    assert context.report["actual_route"] == "renderer"
    assert context.report["renderer_status"] == "completed"
    assert context.report["renderer_calls"] == 1
    assert context.report["artifact_nonempty"] is True
    plt.close("all")


def test_narrative_contract_requires_step4_but_step2_only_outputs_evidence() -> None:
    contract = {
        "answer_shape": "narrative",
        "presentation": ["text"],
        "confidence": "high",
    }

    context = prepare_template_execution("BASE", _enhancement(contract))

    assert context.report["requires_insight"] is True
    assert "evidence text／table" in context.system_prompt
    assert "不直接撰寫最終建議" in context.system_prompt


def test_single_redundant_heatmap_wrapper_is_normalized() -> None:
    contract = {
        "answer_shape": "records",
        "presentation": ["heatmap"],
        "confidence": "high",
    }
    context = prepare_template_execution("BASE", _enhancement(contract))

    result = context.extended_globals["render_output"](
        "heatmap",
        {"heatmap": {"x": [0.1, 0.2], "y": [0.3, 0.4], "weights": None}},
    )

    assert hasattr(result, "savefig")
    assert context.report["payload_normalized"] is True
    assert context.report["artifact_nonempty"] is True
    assert context.report["renderer_status"] == "completed"
    plt.close("all")


def test_missing_heatmap_coordinates_falls_back_instead_of_blank_success(
    capsys,
) -> None:
    contract = {
        "answer_shape": "records",
        "presentation": ["heatmap"],
        "confidence": "high",
    }
    context = prepare_template_execution("BASE", _enhancement(contract))

    result = context.extended_globals["render_output"](
        "heatmap",
        {"heatmap": {}},
    )

    assert isinstance(result, str)
    assert context.report["renderer_status"] == "fallback"
    assert context.report["artifact_nonempty"] is False
    assert "缺少必要欄位" in context.report["fallback_reason"]
    assert "payload 無法安全轉為文字" in capsys.readouterr().out
    assert plt.get_fignums() == []


def test_valid_empty_heatmap_is_reported_empty_not_completed() -> None:
    contract = {
        "answer_shape": "records",
        "presentation": ["heatmap"],
        "confidence": "high",
    }
    context = prepare_template_execution("BASE", _enhancement(contract))

    result = context.extended_globals["render_output"](
        "heatmap",
        {"x": [], "y": [], "weights": None},
    )

    assert hasattr(result, "savefig")
    assert context.report["actual_route"] == "renderer"
    assert context.report["renderer_status"] == "empty"
    assert context.report["artifact_nonempty"] is False
    plt.close("all")


def test_nonempty_payload_cannot_succeed_with_blank_figure(monkeypatch) -> None:
    contract = {
        "answer_shape": "records",
        "presentation": ["heatmap"],
        "confidence": "high",
    }
    context = prepare_template_execution("BASE", _enhancement(contract))
    monkeypatch.setitem(
        __import__(
            "LLM_as_a_Judge.test_output_adapter",
            fromlist=["_RENDERERS"],
        )._RENDERERS,
        "heatmap",
        lambda payload, title="": plt.figure(),
    )

    result = context.extended_globals["render_output"](
        "heatmap",
        {"x": [0.1], "y": [0.2], "weights": None},
    )

    assert isinstance(result, str)
    assert context.report["renderer_status"] == "fallback"
    assert "未產生可見 artifact" in context.report["fallback_reason"]
    assert plt.get_fignums() == []


def test_renderer_error_falls_back_to_text_without_raising(capsys) -> None:
    contract = {
        "answer_shape": "records",
        "presentation": ["pie"],
        "explicitly_requested": True,
        "confidence": "high",
    }
    context = prepare_template_execution("BASE", _enhancement(contract))
    result = context.extended_globals["render_output"](
        "pie",
        {
            "series": [{
                "name": "比例",
                "labels": ["甲", "乙"],
                "values": [2, -1],
            }]
        },
    )

    assert isinstance(result, str)
    assert "甲: 2" in capsys.readouterr().out
    assert context.report["actual_route"] == "generic_text_fallback"
    assert context.report["renderer_status"] == "fallback"
    assert "負值" in context.report["fallback_reason"]
    assert plt.get_fignums() == []


def test_presentation_mismatch_falls_back_without_changing_payload(capsys) -> None:
    contract = {
        "answer_shape": "scalar",
        "presentation": ["text"],
        "explicitly_requested": False,
        "confidence": "high",
    }
    context = prepare_template_execution("BASE", _enhancement(contract))
    context.extended_globals["render_output"](
        "bar",
        {"series": [{"name": "值", "labels": ["甲"], "values": [7]}]},
    )

    assert "甲: 7" in capsys.readouterr().out
    assert "合約不一致" in context.report["fallback_reason"]


def test_missing_render_call_uses_existing_free_code_without_retry() -> None:
    contract = {
        "answer_shape": "table",
        "presentation": ["table"],
        "explicitly_requested": False,
        "confidence": "medium",
    }
    context = prepare_template_execution("BASE", _enhancement(contract))
    report = finalize_template_report(context.report)

    assert report["actual_route"] == "existing_free_code"
    assert report["fallback_reason"] == "render_output_not_called"
    assert report["renderer_calls"] == 0


def test_composite_cannot_add_presentation_outside_contract(capsys) -> None:
    contract = {
        "answer_shape": "composite",
        "presentation": ["text", "table"],
        "explicitly_requested": False,
        "confidence": "high",
    }
    context = prepare_template_execution("BASE", _enhancement(contract))
    context.extended_globals["render_output"](
        "composite",
        {
            "items": [{
                "kind": "bar",
                "payload": {
                    "series": [{"name": "值", "labels": ["甲"], "values": [1]}]
                },
            }]
        },
    )

    assert "甲: 1" in capsys.readouterr().out
    assert context.report["actual_route"] == "generic_text_fallback"
    assert "composite item" in context.report["fallback_reason"]


def test_code_token_split_is_explicitly_estimated_and_conserved() -> None:
    code = """value = df['x'].sum()
output_payload = {'label': '總和', 'value': value}
template_output = render_output('text', output_payload)
"""
    split = estimate_code_token_split(code, 30)

    assert split["presentation_output_tokens_estimated"] > 0
    assert (
        split["analysis_output_tokens_estimated"]
        + split["presentation_output_tokens_estimated"]
        == 30
    )

    prompt_split = estimate_prompt_token_split(
        "BASE",
        "BASE plus rendering instruction",
        "question",
        40,
    )
    assert prompt_split["presentation_input_tokens_estimated"] > 0
    assert sum(prompt_split.values()) == 40
