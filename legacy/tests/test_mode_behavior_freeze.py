"""Phase 2.5：五種 mode 的既有分析行為凍結測試。"""

import importlib

import pytest

from LLM_as_a_Judge.LLM_as_a_Judge import LLMAsAJudge
from LLM_as_a_Judge.evaluation_records import EvaluationLedger
from LLM_as_a_Judge.mode_config import SUPPORTED_MODES


evaluator_module = importlib.import_module("LLM_as_a_Judge.LLM_as_a_Judge")


def _evaluator(mode):
    evaluator = object.__new__(LLMAsAJudge)
    evaluator.mode = mode
    evaluator.data_schema_info = "FULL_SCHEMA"
    evaluator.column_definitions_info = "FULL_DEFINITIONS"
    evaluator.court_place_info = "FULL_COURT"
    return evaluator


@pytest.mark.parametrize(
    ("mode", "expected_builder", "expected_args"),
    [
        (
            "baseline_minimal",
            "minimal",
            ("FULL_SCHEMA",),
        ),
        (
            "baseline_metadata",
            "metadata",
            ("FULL_SCHEMA", "FULL_DEFINITIONS", "FULL_COURT"),
        ),
        (
            "baseline_fullprompt",
            "full",
            ("FULL_SCHEMA", "FULL_DEFINITIONS", "FULL_COURT"),
        ),
        (
            "our_method",
            "full",
            ("FILTERED_SCHEMA", "FILTERED_DEFINITIONS", "FULL_COURT"),
        ),
        (
            "test",
            "full",
            ("FILTERED_SCHEMA", "FILTERED_DEFINITIONS", "FULL_COURT"),
        ),
    ],
)
def test_mode_prompt_builder_and_metadata_are_frozen(
    mode,
    expected_builder,
    expected_args,
    monkeypatch,
) -> None:
    calls = []

    def builder(name):
        def fake(*args):
            calls.append((name, args))
            return f"PROMPT:{name}"

        return fake

    monkeypatch.setattr(evaluator_module, "create_minimal_system_prompt", builder("minimal"))
    monkeypatch.setattr(evaluator_module, "create_metadata_system_prompt", builder("metadata"))
    monkeypatch.setattr(evaluator_module, "create_system_prompt", builder("full"))
    monkeypatch.setattr(
        evaluator_module,
        "create_court_metadata_priority_instruction",
        lambda: "|COURT_PRIORITY|",
    )
    monkeypatch.setattr(
        evaluator_module,
        "filter_schema_and_definitions",
        lambda *args: ("FILTERED_SCHEMA", "FILTERED_DEFINITIONS"),
    )

    prompt = _evaluator(mode)._build_system_prompt(["shot_type"], True)

    assert calls == [(expected_builder, expected_args)]
    if mode in {"our_method", "test"}:
        assert prompt == "PROMPT:full|COURT_PRIORITY|"
    else:
        assert prompt == f"PROMPT:{expected_builder}"


@pytest.mark.parametrize("mode", ("our_method", "test"))
def test_filtered_modes_keep_court_gate_false(mode, monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        evaluator_module,
        "filter_schema_and_definitions",
        lambda *args: ("FILTERED_SCHEMA", "FILTERED_DEFINITIONS"),
    )
    monkeypatch.setattr(
        evaluator_module,
        "create_system_prompt",
        lambda *args: calls.append(args) or "PROMPT",
    )

    prompt = _evaluator(mode)._build_system_prompt(["shot_type"], False)

    assert prompt == "PROMPT"
    assert calls == [("FILTERED_SCHEMA", "FILTERED_DEFINITIONS", None)]


def test_supported_mode_set_is_frozen() -> None:
    assert SUPPORTED_MODES == (
        "baseline_minimal",
        "baseline_metadata",
        "baseline_fullprompt",
        "our_method",
        "test",
    )


@pytest.mark.parametrize(
    ("mode", "expected_workflow"),
    [
        ("baseline_minimal", ["code_generation", "execution"]),
        ("baseline_metadata", ["code_generation", "execution"]),
        ("baseline_fullprompt", ["code_generation", "execution"]),
        ("our_method", ["step1", "code_generation", "execution"]),
        ("test", ["step1", "code_generation", "execution"]),
    ],
)
def test_mode_pipeline_stage_order_and_repair_limit_are_frozen(
    mode,
    expected_workflow,
    monkeypatch,
    tmp_path,
) -> None:
    evaluator = _evaluator(mode)
    evaluator.enable_step1 = mode in {"our_method", "test"}
    evaluator.enable_output_template_lab = mode == "test"
    evaluator.skip_insight = True
    evaluator.gen_model = "fake"
    evaluator.gen_client = object()
    evaluator.df = object()
    evaluator._current_q_num = 1
    evaluator.plots_dir = str(tmp_path)
    evaluator.step1_route_records = []
    evaluator.insight_records = []
    evaluator.ledger = EvaluationLedger()
    workflow = []

    def fake_step1(*args, **kwargs):
        workflow.append("step1")
        return {
            "enhanced_prompt": "enhanced",
            "needs_court_info": False,
            "required_column_groups": ["shot_type"],
            "input_tokens": 1,
            "output_tokens": 1,
            "total_tokens": 2,
        }

    def fake_generation(*args, **kwargs):
        workflow.append("code_generation")
        return {
            "code": "print('ok')",
            "input_tokens": 2,
            "output_tokens": 1,
            "total_tokens": 3,
        }

    def fake_execution(*args, **kwargs):
        workflow.append("execution")
        assert kwargs["max_retries"] == 3
        return {
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
        }

    monkeypatch.setattr(
        evaluator_module,
        "run_prompt_enhancement",
        fake_step1,
    )
    monkeypatch.setattr(
        evaluator_module,
        "run_code_generation",
        fake_generation,
    )
    monkeypatch.setattr(
        evaluator_module,
        "run_code_execution_loop",
        fake_execution,
    )

    result = evaluator._run_pipeline("問題")

    assert workflow == expected_workflow
    assert result[0] == "print('ok')"
    assert result[1] == "已依 SKIP_INSIGHT 設定略過洞察生成。"
