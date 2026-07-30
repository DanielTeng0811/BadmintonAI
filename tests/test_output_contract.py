"""Phase 3：test mode 輸出契約的純離線測試。"""

import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from config.prompts import (
    create_enhancement_system_prompt,
    create_test_enhancement_system_prompt,
)
from LLM_as_a_Judge.LLM_as_a_Judge import LLMAsAJudge
from LLM_as_a_Judge.evaluation_records import EvaluationLedger
from LLM_as_a_Judge.output_contract import validate_output_contract
from utils.analysis_workflow import run_prompt_enhancement


evaluator_module = importlib.import_module("LLM_as_a_Judge.LLM_as_a_Judge")


class _FakeCompletions:
    def __init__(self, content):
        self.content = content
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        return SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content=self.content)
            )],
            usage=SimpleNamespace(
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
            ),
        )


def _run_contract(content, question="測試問題"):
    completions = _FakeCompletions(content)
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=completions)
    )
    result = run_prompt_enhancement(
        client,
        "fake-model",
        create_test_enhancement_system_prompt(),
        question,
        [],
        output_contract_validator=validate_output_contract,
    )
    return result, completions.calls


def _step1_response(contract):
    return json.dumps(
        {
            "analysis_subject": "周天成",
            "analysis_unit": "單拍",
            "temporal_requirement": "無",
            "scoring_rule": "無",
            "spatial_requirement": "無",
            "needs_court_info": False,
            "is_related_to_previous_code": False,
            "required_column_groups": ["shot_type"],
            "output_contract": contract,
        },
        ensure_ascii=False,
    )


def test_test_prompt_adds_small_contract_without_changing_base_prompt() -> None:
    base = create_enhancement_system_prompt()
    test_prompt = create_test_enhancement_system_prompt()

    assert "output_contract" not in base
    assert test_prompt.startswith(base[:-1])
    assert "不要輸出其他文字" in test_prompt
    assert "不得加入欄位" in test_prompt
    assert '"presentation": ["text"]' in test_prompt
    assert '"explicitly_requested"' not in test_prompt
    assert len(test_prompt) - len(base) <= 450


def test_compact_contract_without_legacy_explicit_flag_is_valid() -> None:
    contract = {
        "answer_shape": "records",
        "presentation": ["heatmap"],
        "confidence": "high",
    }

    result, calls = _run_contract(_step1_response(contract))

    assert calls == 1
    assert result["output_contract_status"] == "valid"
    assert result["normalized_result"]["output_contract"] == contract


@pytest.mark.parametrize(
    "contract",
    [
        {
            "answer_shape": "records",
            "presentation": ["heatmap", "text"],
            "explicitly_requested": True,
            "confidence": "high",
        },
        {
            "answer_shape": "scalar",
            "presentation": ["text"],
            "explicitly_requested": False,
            "confidence": "high",
        },
        {
            "answer_shape": "narrative",
            "presentation": ["text"],
            "explicitly_requested": False,
            "confidence": "medium",
        },
        {
            "answer_shape": "composite",
            "presentation": ["text", "table", "bar"],
            "explicitly_requested": False,
            "confidence": "medium",
        },
    ],
)
def test_explicit_chart_scalar_narrative_and_multi_output(contract) -> None:
    result, calls = _run_contract(_step1_response(contract))

    assert calls == 1
    assert result["output_contract_status"] == "valid"
    assert result["output_contract_route"] == "renderer_candidate"
    assert result["normalized_result"]["output_contract"] == contract


def test_low_confidence_uses_existing_code_without_retry() -> None:
    contract = {
        "answer_shape": "narrative",
        "presentation": ["text"],
        "explicitly_requested": False,
        "confidence": "low",
    }
    result, calls = _run_contract(_step1_response(contract))

    assert calls == 1
    assert result["output_contract_status"] == "valid"
    assert result["output_contract_route"] == "existing_free_code"


def test_invalid_contract_does_not_get_repaired_or_change_question() -> None:
    invalid = {
        "answer_shape": "table",
        "presentation": ["bar"],
        "explicitly_requested": False,
        "confidence": "high",
        "filters": {"player": "周天成"},
    }
    result, calls = _run_contract(
        _step1_response(invalid),
        question="原始問題不得改寫",
    )

    assert calls == 1
    assert result["output_contract_status"] == "invalid"
    assert result["output_contract_route"] == "existing_free_code"
    assert result["normalized_result"]["output_contract"] is None
    assert "不允許額外欄位" in result["output_contract_errors"][0]
    assert result["enhanced_prompt"].startswith("原始問題不得改寫")


def test_malformed_step1_json_reports_both_parse_and_contract_errors_once() -> None:
    result, calls = _run_contract("不是 JSON")

    assert calls == 1
    assert result["parse_error"]
    assert result["output_contract_status"] == "invalid"
    assert result["output_contract_errors"]
    assert result["enhanced_prompt"] == "測試問題"


@pytest.mark.parametrize(
    "raw_content",
    ['[]', '{"output_contract": {"presentation": [{"bad": true}]}}'],
)
def test_non_object_or_nested_non_string_values_degrade_without_crash(
    raw_content,
) -> None:
    result, calls = _run_contract(raw_content)

    assert calls == 1
    assert result["output_contract_status"] == "invalid"
    assert result["output_contract_route"] == "existing_free_code"


def test_validator_rejects_free_chart_parameters_and_unbounded_outputs() -> None:
    result = validate_output_contract(
        {
            "answer_shape": "records",
            "presentation": ["text", "table", "bar", "line"],
            "explicitly_requested": True,
            "confidence": "high",
            "title": "模型自由標題",
        }
    )

    assert result["status"] == "invalid"
    assert result["route"] == "existing_free_code"
    assert any("額外欄位" in error for error in result["errors"])
    assert any("最多三種" in error for error in result["errors"])


def test_inventory_covers_all_100_questions_without_runtime_routing() -> None:
    inventory_path = (
        Path(__file__).parent / "fixtures" / "phase3_output_inventory.json"
    )
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    shape_groups = inventory["primary_answer_shape"]
    covered = [question_id for ids in shape_groups.values() for question_id in ids]

    assert sorted(covered) == list(range(1, 101))
    assert len(covered) == len(set(covered))
    assert set(shape_groups) == {
        "scalar", "records", "table", "narrative", "composite"
    }
    assert inventory["reference_notebook_presentation"]["text"] == 100


def test_contract_trace_is_available_in_manifest_without_enabling_renderer() -> None:
    evaluator = _pipeline_evaluator("test")
    evaluator.target_questions = [1]
    evaluator.gen_model = "fake-gen"
    evaluator.judge_model = "fake-judge"
    evaluator.skip_insight = True
    evaluator.only_generation = True
    evaluator.input_token_price = 0
    evaluator.output_token_price = 0
    evaluator.judge_input_token_price = None
    evaluator.judge_output_token_price = None
    evaluator._record_step1_route(
        {
            "normalized_result": {
                "output_contract": {
                    "answer_shape": "scalar",
                    "presentation": ["text"],
                    "explicitly_requested": False,
                    "confidence": "high",
                }
            },
            "output_contract_status": "valid",
            "output_contract_route": "renderer_candidate",
            "output_contract_errors": [],
        },
        [],
        False,
    )

    trace = evaluator._build_run_manifest()["step1_routes"][0]
    assert trace["output_contract_status"] == "valid"
    assert trace["output_contract_route"] == "renderer_candidate"
    assert trace["output_template_lab_enabled"] is True


def _pipeline_evaluator(mode):
    evaluator = object.__new__(LLMAsAJudge)
    evaluator.mode = mode
    evaluator.enable_step1 = True
    evaluator.enable_output_template_lab = mode == "test"
    evaluator.skip_insight = True
    evaluator.gen_model = "fake"
    evaluator.gen_client = object()
    evaluator.df = object()
    evaluator._current_q_num = 1
    evaluator.plots_dir = "."
    evaluator.data_schema_info = "schema"
    evaluator.column_definitions_info = "definitions"
    evaluator.court_place_info = "court"
    evaluator.step1_route_records = []
    evaluator.insight_records = []
    evaluator.ledger = EvaluationLedger()
    return evaluator


@pytest.mark.parametrize(
    ("mode", "expects_validator"),
    [("our_method", False), ("test", True)],
)
def test_pipeline_keeps_one_step1_call_and_isolates_contract(
    mode,
    expects_validator,
    monkeypatch,
) -> None:
    evaluator = _pipeline_evaluator(mode)
    step1_calls = []

    def fake_step1(*args, **kwargs):
        step1_calls.append((args[2], kwargs.get("output_contract_validator")))
        return {
            "enhanced_prompt": "問題",
            "needs_court_info": False,
            "required_column_groups": [],
            "normalized_result": {},
            "input_tokens": 1,
            "output_tokens": 1,
            "total_tokens": 2,
        }

    monkeypatch.setattr(evaluator_module, "run_prompt_enhancement", fake_step1)
    monkeypatch.setattr(
        evaluator_module,
        "run_code_generation",
        lambda *args, **kwargs: {
            "code": "print('ok')",
            "input_tokens": 1,
            "output_tokens": 1,
            "total_tokens": 2,
        },
    )
    monkeypatch.setattr(
        evaluator_module,
        "run_code_execution_loop",
        lambda *args, **kwargs: {
            "final_code": "print('ok')",
            "exec_result": {
                "success": True,
                "error": "",
                "figs": [],
                "summary_info": {},
                "stdout": "ok",
            },
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "success": True,
            "repair_attempts": 0,
            "attempt_usages": [],
        },
    )

    evaluator._run_pipeline("問題")

    assert len(step1_calls) == 1
    prompt, validator = step1_calls[0]
    assert (validator is validate_output_contract) is expects_validator
    assert ("output_contract" in prompt) is expects_validator
