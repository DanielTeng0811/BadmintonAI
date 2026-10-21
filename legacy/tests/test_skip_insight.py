"""Phase 2：全模式 SKIP_INSIGHT 的純離線測試。"""

import importlib
import inspect

import pytest

from LLM_as_a_Judge.LLM_as_a_Judge import LLMAsAJudge
from LLM_as_a_Judge.mode_config import SUPPORTED_MODES


evaluator_module = importlib.import_module("LLM_as_a_Judge.LLM_as_a_Judge")


def _evaluator(mode: str, skip_insight: bool):
    evaluator = object.__new__(LLMAsAJudge)
    evaluator.mode = mode
    evaluator.skip_insight = skip_insight
    evaluator.gen_client = object()
    evaluator.gen_model = "fake-model"
    evaluator._current_q_num = 1
    evaluator.insight_records = []
    return evaluator


def test_skip_insight_defaults_to_false() -> None:
    parameter = inspect.signature(LLMAsAJudge.__init__).parameters["skip_insight"]

    assert parameter.default is False


@pytest.mark.parametrize("mode", SUPPORTED_MODES)
def test_skip_insight_avoids_llm_call_and_returns_zero_tokens(
    mode,
    monkeypatch,
) -> None:
    calls = []
    monkeypatch.setattr(
        evaluator_module,
        "run_insight_generation",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    evaluator = _evaluator(mode, skip_insight=True)

    result = evaluator._run_insight_step("問題", "執行結果")

    assert calls == []
    assert result == {
        "insight": "已依 SKIP_INSIGHT 設定略過洞察生成。",
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "status": "skipped",
        "skipped": True,
    }


@pytest.mark.parametrize("mode", SUPPORTED_MODES)
def test_insight_enabled_keeps_existing_call_and_tokens(mode, monkeypatch) -> None:
    calls = []

    def fake_insight(*args, **kwargs):
        calls.append((args, kwargs))
        return {
            "insight": "正常洞察",
            "input_tokens": 13,
            "output_tokens": 5,
            "total_tokens": 18,
        }

    monkeypatch.setattr(evaluator_module, "run_insight_generation", fake_insight)
    evaluator = _evaluator(mode, skip_insight=False)

    result = evaluator._run_insight_step("問題", "執行結果")

    assert len(calls) == 1
    assert result["insight"] == "正常洞察"
    assert result["input_tokens"] == 13
    assert result["output_tokens"] == 5
    assert result["status"] == "generated"
    assert result["skipped"] is False


def test_insight_record_drives_csv_fields_and_notebook_marker() -> None:
    evaluator = _evaluator("test", skip_insight=True)
    evaluator._record_insight_usage(
        {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "status": "skipped",
            "skipped": True,
        }
    )

    assert evaluator._current_insight_fields() == {
        "skip_insight": True,
        "insight_status": "skipped",
        "insight_input_tokens": 0,
        "insight_output_tokens": 0,
        "insight_tokens": 0,
        "requires_insight": False,
        "evaluation_gate": "code_logic",
        "answer_completion_status": "analysis_complete_insight_skipped",
    }
    assert "已依 SKIP_INSIGHT 設定略過" in evaluator._insight_markdown("")


def test_summary_reports_global_and_per_question_insight_usage() -> None:
    evaluator = _evaluator("our_method", skip_insight=True)
    evaluator.target_questions = [1]
    evaluator.total_pipeline_input_tokens = 10
    evaluator.total_pipeline_output_tokens = 4
    evaluator.total_judge_tokens = 0
    evaluator.input_token_price = 1
    evaluator.output_token_price = 1
    evaluator.judge_model = "fake-judge"
    evaluator.only_generation = True
    evaluator.results = []
    evaluator.step1_route_records = []
    evaluator._record_insight_usage(
        {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "status": "skipped",
            "skipped": True,
        }
    )

    summary = evaluator._build_summary_text()

    assert "SKIP_INSIGHT: True" in summary
    assert "洞察 Token (input/output): 0/0" in summary
    assert "評估 gate: code_logic" in summary
    assert (
        "Q1: status=skipped, skipped=True, "
        "completion=analysis_complete_insight_skipped, input=0, output=0"
    ) in summary

    manifest = evaluator._build_run_manifest()
    assert manifest["settings"]["skip_insight"] is True
    assert manifest["insight"]["input_tokens"] == 0
    assert manifest["insight"]["output_tokens"] == 0
    assert manifest["insight"]["questions"][0]["status"] == "skipped"
    assert manifest["evaluation"]["gate"] == "code_logic"


def test_only_generation_does_not_override_skip_insight() -> None:
    evaluator = _evaluator("test", skip_insight=True)
    evaluator._load_target_questions = lambda: []

    evaluator.run(only_generation=False)
    assert evaluator.skip_insight is True

    evaluator.run(only_generation=True)
    assert evaluator.skip_insight is True
