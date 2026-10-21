"""Phase 2.5 評估 ledger 的純離線測試。"""

import pytest

from LLM_as_a_Judge.evaluation_records import EvaluationLedger
from utils import analysis_workflow


def test_ledger_keeps_stage_tokens_and_repair_attempts() -> None:
    ledger = EvaluationLedger()
    ledger.start_question(1, "問題")
    ledger.record_stage(
        1,
        "step1",
        {"input_tokens": 10, "output_tokens": 2},
        model="fake",
    )
    ledger.record_stage(
        1,
        "repair",
        {"input_tokens": 20, "output_tokens": 5},
        attempt=1,
        model="fake",
    )

    assert ledger.usage_for_question(1) == {
        "input_tokens": 30,
        "output_tokens": 7,
        "total_tokens": 37,
        "calls": 2,
    }
    assert ledger.stage_dicts()[1]["attempt"] == 1


def test_question_status_is_independent_of_judge() -> None:
    ledger = EvaluationLedger()
    ledger.start_question(7, "問題")

    ledger.update_question(
        7,
        status="execution_failed",
        execution_success=False,
        execution_error="ValueError",
        repair_attempts=3,
        judge_status="not_run_execution_failed",
        needs_review=True,
    )

    record = ledger.question_dicts()[0]
    assert record["execution_success"] is False
    assert record["judge_status"] == "not_run_execution_failed"
    assert record["repair_attempts"] == 3


def test_unknown_question_field_is_rejected() -> None:
    ledger = EvaluationLedger()
    ledger.start_question(1, "問題")

    with pytest.raises(ValueError, match="未知的題目狀態欄位"):
        ledger.update_question(1, unknown=True)


def test_repair_loop_reports_each_attempt_without_changing_retry_count(
    monkeypatch,
) -> None:
    executions = iter([
        {"success": False, "error": "first"},
        {"success": True, "error": ""},
    ])
    monkeypatch.setattr(
        analysis_workflow,
        "run_code_execution",
        lambda *args, **kwargs: next(executions),
    )
    monkeypatch.setattr(
        analysis_workflow,
        "log_llm_interaction",
        lambda *args, **kwargs: None,
    )

    class Completions:
        def create(self, **kwargs):
            message = type("Message", (), {"content": "python"})
            choice = type("Choice", (), {"message": message})
            usage = type(
                "Usage",
                (),
                {
                    "prompt_tokens": 9,
                    "completion_tokens": 3,
                    "total_tokens": 12,
                },
            )
            return type(
                "Response",
                (),
                {"choices": [choice], "usage": usage},
            )

    client = type(
        "Client",
        (),
        {
            "chat": type(
                "Chat",
                (),
                {"completions": Completions()},
            )
        },
    )

    result = analysis_workflow.run_code_execution_loop(
        client,
        "fake",
        "print('x')",
        object(),
        "system",
        "question",
        max_retries=3,
    )

    assert result["success"] is True
    assert result["repair_attempts"] == 1
    assert result["attempt_usages"] == [
        {
            "attempt": 1,
            "input_tokens": 9,
            "output_tokens": 3,
            "total_tokens": 12,
        }
    ]
