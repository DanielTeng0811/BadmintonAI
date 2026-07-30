"""Phase 2.5：失敗狀態、缺 reference 與報表一致性的離線測試。"""

import importlib
from types import SimpleNamespace

import pytest

from LLM_as_a_Judge.LLM_as_a_Judge import (
    LLMAsAJudge,
    PipelineExecutionError,
)
from LLM_as_a_Judge.evaluation_records import EvaluationLedger


evaluator_module = importlib.import_module("LLM_as_a_Judge.LLM_as_a_Judge")


def _bare_evaluator(mode="baseline_minimal"):
    evaluator = object.__new__(LLMAsAJudge)
    evaluator.mode = mode
    evaluator.gen_model = "fake-gen"
    evaluator.judge_model = "fake-judge"
    evaluator.enable_step1 = False
    evaluator.enable_output_template_lab = mode == "test"
    evaluator.skip_insight = False
    evaluator.data_schema_info = "schema"
    evaluator.column_definitions_info = "definitions"
    evaluator.court_place_info = "court"
    evaluator.results = []
    evaluator.notebook = evaluator._create_notebook_structure()
    evaluator.reference_answers = {}
    evaluator.flagged_questions = []
    evaluator.step1_route_records = []
    evaluator.insight_records = []
    evaluator.ledger = EvaluationLedger()
    evaluator.total_pipeline_input_tokens = 0
    evaluator.total_pipeline_output_tokens = 0
    evaluator.total_judge_tokens = 0
    evaluator.target_questions = [1]
    evaluator.input_token_price = 1
    evaluator.output_token_price = 1
    evaluator.example_file = "example.ipynb"
    evaluator._checkpoint_export = lambda: None
    evaluator._load_target_questions = lambda: [
        {"編號": 1, "問題": "問題"}
    ]
    return evaluator


def _successful_pipeline(evaluator):
    def run_pipeline(prompt):
        evaluator._record_stage_usage(
            "code_generation",
            {"input_tokens": 10, "output_tokens": 4},
        )
        evaluator._record_stage_usage(
            "execution",
            status="completed",
            calls=0,
        )
        evaluator.ledger.update_question(
            1,
            status="execution_succeeded",
            execution_success=True,
        )
        return ("print('ok')", "", [], [], 10, 4, [])

    return run_pipeline


def test_missing_reference_keeps_result_tokens_and_skips_judge() -> None:
    evaluator = _bare_evaluator()
    evaluator._run_pipeline = _successful_pipeline(evaluator)
    evaluator._judge_result = lambda *args: pytest.fail(
        "缺 reference 不得呼叫 Judge"
    )

    evaluator.run(only_generation=False)

    assert len(evaluator.results) == 1
    result = evaluator.results[0]
    assert result["pipeline_tokens"] == 14
    assert result["judge_status"] == "reference_missing"
    assert result["code_correct"] is None
    assert evaluator.total_pipeline_input_tokens == 10
    assert evaluator.total_pipeline_output_tokens == 4


def test_only_generation_still_creates_structured_question_result() -> None:
    evaluator = _bare_evaluator()
    evaluator._run_pipeline = _successful_pipeline(evaluator)

    evaluator.run(only_generation=True)

    assert len(evaluator.results) == 1
    assert evaluator.results[0]["judge_status"] == "skipped_only_generation"
    assert evaluator.results[0]["judge_tokens"] == 0


def test_execution_failure_stops_before_insight_and_preserves_usage(
    monkeypatch,
    tmp_path,
) -> None:
    evaluator = _bare_evaluator()
    evaluator._current_q_num = 1
    evaluator.ledger.start_question(1, "問題")
    evaluator.gen_client = object()
    evaluator.df = object()
    evaluator.plots_dir = str(tmp_path)
    evaluator._build_system_prompt = lambda *args: "system"
    monkeypatch.setattr(
        evaluator_module,
        "run_code_generation",
        lambda *args, **kwargs: {
            "code": "print('broken')",
            "input_tokens": 11,
            "output_tokens": 5,
            "total_tokens": 16,
        },
    )
    monkeypatch.setattr(
        evaluator_module,
        "run_code_execution_loop",
        lambda *args, **kwargs: {
            "final_code": "print('still broken')",
            "exec_result": {
                "success": False,
                "error": "ValueError: broken",
                "figs": [],
                "summary_info": {},
                "stdout": "",
            },
            "input_tokens": 7,
            "output_tokens": 3,
            "total_tokens": 10,
            "success": False,
            "repair_attempts": 1,
            "attempt_usages": [
                {
                    "attempt": 1,
                    "input_tokens": 7,
                    "output_tokens": 3,
                    "total_tokens": 10,
                }
            ],
        },
    )
    monkeypatch.setattr(
        evaluator_module,
        "run_insight_generation",
        lambda *args, **kwargs: pytest.fail(
            "execution_failed 不得呼叫 insight"
        ),
    )

    with pytest.raises(PipelineExecutionError, match="broken"):
        evaluator._run_pipeline("問題")

    assert evaluator.ledger.questions[1].status == "execution_failed"
    assert evaluator.ledger.questions[1].repair_attempts == 1
    assert evaluator._question_pipeline_usage(1) == {
        "input_tokens": 18,
        "output_tokens": 8,
        "total_tokens": 26,
        "calls": 2,
    }
    assert {
        item.stage for item in evaluator.ledger.stage_usages
    } == {"step1", "code_generation", "repair", "execution"}


def test_successful_repair_is_recorded_and_pipeline_continues(
    monkeypatch,
    tmp_path,
) -> None:
    evaluator = _bare_evaluator()
    evaluator.skip_insight = True
    evaluator._current_q_num = 1
    evaluator.ledger.start_question(1, "問題")
    evaluator.gen_client = object()
    evaluator.df = object()
    evaluator.plots_dir = str(tmp_path)
    evaluator._build_system_prompt = lambda *args: "system"
    monkeypatch.setattr(
        evaluator_module,
        "run_code_generation",
        lambda *args, **kwargs: {
            "code": "print('broken')",
            "input_tokens": 4,
            "output_tokens": 2,
            "total_tokens": 6,
        },
    )
    monkeypatch.setattr(
        evaluator_module,
        "run_code_execution_loop",
        lambda *args, **kwargs: {
            "final_code": "print('fixed')",
            "exec_result": {
                "success": True,
                "error": "",
                "figs": [],
                "summary_info": {},
                "stdout": "fixed",
            },
            "input_tokens": 8,
            "output_tokens": 3,
            "total_tokens": 11,
            "success": True,
            "repair_attempts": 1,
            "attempt_usages": [
                {
                    "attempt": 1,
                    "input_tokens": 8,
                    "output_tokens": 3,
                    "total_tokens": 11,
                }
            ],
        },
    )

    result = evaluator._run_pipeline("問題")

    assert result[0] == "print('fixed')"
    assert evaluator.ledger.questions[1].execution_success is True
    assert evaluator.ledger.questions[1].repair_attempts == 1
    repair = evaluator.ledger.usage_for_stage("repair")
    assert repair["total_tokens"] == 11
    assert repair["calls"] == 1


def test_atomic_write_failure_keeps_previous_report(
    monkeypatch,
    tmp_path,
) -> None:
    evaluator = _bare_evaluator()
    target = tmp_path / "summary.txt"
    target.write_text("previous", encoding="utf-8")
    monkeypatch.setattr(
        evaluator_module.os,
        "replace",
        lambda *args: (_ for _ in ()).throw(OSError("replace failed")),
    )

    with pytest.raises(OSError, match="replace failed"):
        evaluator._atomic_write_text(str(target), "new")

    assert target.read_text(encoding="utf-8") == "previous"
    assert not (tmp_path / "summary.txt.tmp").exists()


def test_cost_summary_uses_separate_generation_and_judge_prices() -> None:
    evaluator = _bare_evaluator()
    evaluator.judge_input_token_price = 2
    evaluator.judge_output_token_price = 4
    evaluator.ledger.start_question(1, "問題")
    evaluator._current_q_num = 1
    evaluator._record_stage_usage(
        "code_generation",
        {"input_tokens": 10, "output_tokens": 3},
    )
    evaluator._record_stage_usage(
        "judge",
        {"input_tokens": 5, "output_tokens": 2},
        model="fake-judge",
    )

    costs = evaluator._build_cost_summary()

    assert costs["generation_cost"] == 13
    assert costs["judge_cost"] == 18
    assert costs["total_cost"] == 31


def test_export_schema_exists_in_only_generation_mode(tmp_path) -> None:
    evaluator = _bare_evaluator()
    evaluator.only_generation = True
    evaluator.results = [
        {
            "question_id": 1,
            "status": "completed",
            "judge_status": "skipped_only_generation",
        }
    ]
    evaluator._current_q_num = 1
    evaluator.ledger.start_question(1, "問題")
    evaluator._record_stage_usage(
        "judge",
        status="skipped_only_generation",
        calls=0,
        model="fake-judge",
    )
    evaluator.csv_file = str(tmp_path / "eval_results.csv")
    evaluator.stage_usage_file = str(tmp_path / "stage_usage.csv")
    evaluator.ipynb_file = str(tmp_path / "eval_notebook.ipynb")
    evaluator.summary_file = str(tmp_path / "summary.txt")
    evaluator.manifest_file = str(tmp_path / "run_manifest.json")
    evaluator.run_dir = str(tmp_path)

    evaluator._export_files(show_message=False)

    for filename in (
        "eval_results.csv",
        "stage_usage.csv",
        "eval_notebook.ipynb",
        "summary.txt",
        "run_manifest.json",
    ):
        assert (tmp_path / filename).exists()


def test_judge_parse_failure_keeps_input_output_tokens() -> None:
    evaluator = _bare_evaluator()
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="不是 JSON")
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=12,
            completion_tokens=4,
            total_tokens=16,
        ),
    )
    evaluator.judge_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **kwargs: response
            )
        )
    )

    result = evaluator._judge_result("問題", "print('ok')", "reference")

    assert result["judge_status"] == "parse_failed"
    assert result["judge_input_tokens"] == 12
    assert result["judge_output_tokens"] == 4
    assert result["judge_tokens"] == 16


def test_later_stage_exception_keeps_completed_stage_tokens(
    monkeypatch,
    tmp_path,
) -> None:
    evaluator = _bare_evaluator("our_method")
    evaluator.enable_step1 = True
    evaluator._current_q_num = 1
    evaluator.ledger.start_question(1, "問題")
    evaluator.gen_client = object()
    evaluator.df = object()
    evaluator.plots_dir = str(tmp_path)
    evaluator._build_system_prompt = lambda *args: "system"
    monkeypatch.setattr(
        evaluator_module,
        "run_prompt_enhancement",
        lambda *args, **kwargs: {
            "enhanced_prompt": "enhanced",
            "needs_court_info": False,
            "required_column_groups": [],
            "input_tokens": 15,
            "output_tokens": 4,
            "total_tokens": 19,
        },
    )
    monkeypatch.setattr(
        evaluator_module,
        "run_code_generation",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("generation failed")
        ),
    )

    with pytest.raises(RuntimeError, match="generation failed"):
        evaluator._run_pipeline("問題")

    assert evaluator.ledger.usage_for_stage("step1")["total_tokens"] == 19
    code_stage = [
        item for item in evaluator.ledger.stage_usages
        if item.stage == "code_generation"
    ][0]
    assert code_stage.status == "failed"
    assert code_stage.calls == 1
