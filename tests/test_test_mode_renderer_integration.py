"""Phase 5：test mode renderer 接線的完整純離線測試。"""

import importlib
from pathlib import Path
import subprocess
import sys

import pandas as pd

from LLM_as_a_Judge.LLM_as_a_Judge import LLMAsAJudge
from LLM_as_a_Judge.evaluation_records import EvaluationLedger


evaluator_module = importlib.import_module("LLM_as_a_Judge.LLM_as_a_Judge")


def _evaluator(tmp_path, mode="test"):
    evaluator = object.__new__(LLMAsAJudge)
    evaluator.mode = mode
    evaluator.enable_step1 = mode in {"test", "our_method"}
    evaluator.enable_output_template_lab = mode == "test"
    evaluator.skip_insight = True
    evaluator.gen_model = "fake"
    evaluator.judge_model = "fake-judge"
    evaluator.gen_client = object()
    evaluator.df = pd.DataFrame({"value": [2, 3, 5]})
    evaluator._current_q_num = 1
    evaluator.plots_dir = str(tmp_path)
    evaluator.data_schema_info = "schema"
    evaluator.column_definitions_info = "definitions"
    evaluator.court_place_info = "court"
    evaluator.step1_route_records = []
    evaluator.template_records = []
    evaluator.insight_records = []
    evaluator.ledger = EvaluationLedger()
    evaluator.target_questions = [1]
    evaluator.results = []
    evaluator.input_token_price = 0
    evaluator.output_token_price = 0
    evaluator.judge_input_token_price = None
    evaluator.judge_output_token_price = None
    evaluator.only_generation = True
    evaluator._build_system_prompt = lambda *args: "BASE_SYSTEM_PROMPT"
    return evaluator


def _step1(contract, status="valid", route="renderer_candidate"):
    return {
        "enhanced_prompt": "原始分析問題",
        "needs_court_info": False,
        "required_column_groups": ["shot_type"],
        "normalized_result": {"output_contract": contract},
        "output_contract_status": status,
        "output_contract_route": route,
        "input_tokens": 8,
        "output_tokens": 4,
        "total_tokens": 12,
    }


def _run_with_code(monkeypatch, evaluator, step1_result, code):
    prompts = []
    monkeypatch.setattr(
        evaluator_module,
        "run_prompt_enhancement",
        lambda *args, **kwargs: step1_result,
    )

    def fake_generation(client, model, system_prompt, *args, **kwargs):
        prompts.append(system_prompt)
        return {
            "code": code,
            "input_tokens": 20,
            "output_tokens": 12,
            "total_tokens": 32,
        }

    monkeypatch.setattr(
        evaluator_module,
        "run_code_generation",
        fake_generation,
    )
    result = evaluator._run_pipeline("原始分析問題")
    return result, prompts


def test_test_mode_renderer_success_keeps_analysis_and_creates_chart(
    monkeypatch,
    tmp_path,
) -> None:
    evaluator = _evaluator(tmp_path)
    contract = {
        "answer_shape": "records",
        "presentation": ["bar"],
        "explicitly_requested": True,
        "confidence": "high",
    }
    code = """total = int(df['value'].sum())
output_payload = {
    'series': [{'name': '數量', 'labels': ['總和'], 'values': [total]}]
}
template_output = render_output('bar', output_payload, '統計結果')
"""

    result, prompts = _run_with_code(
        monkeypatch,
        evaluator,
        _step1(contract),
        code,
    )

    assert "render_output(kind, payload" in prompts[0]
    assert "matplotlib／seaborn" in prompts[0]
    assert len(result[2]) == 1
    record = evaluator.template_records[0]
    assert record["actual_route"] == "renderer"
    assert record["renderer_calls"] == 1
    assert record["presentation_output_tokens_estimated"] > 0
    assert (
        record["analysis_output_tokens_estimated"]
        + record["presentation_output_tokens_estimated"]
        == 12
    )
    assert (
        record["analysis_input_tokens_estimated"]
        + record["presentation_input_tokens_estimated"]
        == 20
    )
    renderer_usage = evaluator.ledger.usage_for_stage("renderer")
    assert renderer_usage == {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "calls": 1,
    }
    manifest_record = evaluator._build_run_manifest()["template"]["questions"][0]
    assert manifest_record["actual_route"] == "renderer"
    summary = evaluator._build_summary_text()
    assert "Code output token 分配為估計值" in summary
    assert "Payload 正規化題號: none" in summary
    assert "空輸出產物題號: none" in summary


def test_narrative_text_does_not_force_chart(monkeypatch, tmp_path) -> None:
    evaluator = _evaluator(tmp_path)
    contract = {
        "answer_shape": "narrative",
        "presentation": ["text"],
        "explicitly_requested": False,
        "confidence": "high",
    }
    code = """total = int(df['value'].sum())
output_payload = {'label': '綜合結果', 'value': f'總和為 {total}'}
template_output = render_output('text', output_payload)
"""

    result, _ = _run_with_code(
        monkeypatch,
        evaluator,
        _step1(contract),
        code,
    )

    assert result[2] == []
    assert evaluator.template_records[0]["actual_route"] == "renderer"
    assert evaluator.template_records[0]["presentation_used"] == "text"
    assert evaluator.template_records[0]["requires_insight"] is True
    insight_fields = evaluator._current_insight_fields()
    assert insight_fields["evaluation_gate"] == "code_logic"
    assert insight_fields["answer_completion_status"] == (
        "evidence_only_insight_skipped"
    )
    assert "最終洞察／建議未產生" in evaluator._insight_markdown("")


def test_renderer_failure_uses_generic_text_without_repair_or_blank_figure(
    monkeypatch,
    tmp_path,
) -> None:
    evaluator = _evaluator(tmp_path)
    contract = {
        "answer_shape": "records",
        "presentation": ["pie"],
        "explicitly_requested": True,
        "confidence": "high",
    }
    code = """values = [2, -1]
output_payload = {
    'series': [{'name': '比例', 'labels': ['甲', '乙'], 'values': values}]
}
template_output = render_output('pie', output_payload)
"""

    result, _ = _run_with_code(
        monkeypatch,
        evaluator,
        _step1(contract),
        code,
    )

    assert result[2] == []
    record = evaluator.template_records[0]
    assert record["actual_route"] == "generic_text_fallback"
    assert record["renderer_status"] == "fallback"
    assert "負值" in record["fallback_reason"]
    assert evaluator.ledger.usage_for_stage("repair")["calls"] == 0
    assert evaluator.ledger.questions[1].execution_success is True


def test_missing_render_call_falls_back_without_extra_call(
    monkeypatch,
    tmp_path,
) -> None:
    evaluator = _evaluator(tmp_path)
    contract = {
        "answer_shape": "scalar",
        "presentation": ["text"],
        "explicitly_requested": False,
        "confidence": "medium",
    }

    result, _ = _run_with_code(
        monkeypatch,
        evaluator,
        _step1(contract),
        "total = int(df['value'].sum())\nprint(total)",
    )

    assert result[2] == []
    record = evaluator.template_records[0]
    assert record["actual_route"] == "existing_free_code"
    assert record["fallback_reason"] == "render_output_not_called"
    assert record["renderer_calls"] == 0
    assert evaluator.ledger.usage_for_stage("repair")["calls"] == 0


def test_invalid_contract_keeps_base_prompt_and_existing_free_code(
    monkeypatch,
    tmp_path,
) -> None:
    evaluator = _evaluator(tmp_path)
    result, prompts = _run_with_code(
        monkeypatch,
        evaluator,
        _step1(None, status="invalid", route="existing_free_code"),
        "total = int(df['value'].sum())\nprint(total)",
    )

    assert prompts == ["BASE_SYSTEM_PROMPT"]
    assert result[2] == []
    record = evaluator.template_records[0]
    assert record["enabled"] is False
    assert record["actual_route"] == "existing_free_code"
    renderer_stage = [
        item for item in evaluator.ledger.stage_usages
        if item.stage == "renderer"
    ][0]
    assert renderer_stage.status == "skipped"
    assert renderer_stage.calls == 0


def test_our_method_never_receives_template_prompt_or_renderer_stage(
    monkeypatch,
    tmp_path,
) -> None:
    evaluator = _evaluator(tmp_path, mode="our_method")
    result, prompts = _run_with_code(
        monkeypatch,
        evaluator,
        _step1({
            "answer_shape": "records",
            "presentation": ["bar"],
            "explicitly_requested": True,
            "confidence": "high",
        }),
        "total = int(df['value'].sum())\nprint(total)",
    )

    assert prompts == ["BASE_SYSTEM_PROMPT"]
    assert result[2] == []
    assert evaluator.template_records[0]["actual_route"] == "disabled"
    assert all(
        item.stage != "renderer" for item in evaluator.ledger.stage_usages
    )


def test_importing_evaluator_does_not_eagerly_load_test_adapter_or_runtime() -> None:
    root = Path(__file__).parents[1]
    source = """import sys
import LLM_as_a_Judge.LLM_as_a_Judge
assert 'LLM_as_a_Judge.test_output_adapter' not in sys.modules
assert 'LLM_as_a_Judge.test_output_runtime' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", source],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
