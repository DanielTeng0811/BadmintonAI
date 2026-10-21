"""Phase 6：固定題組與六類輸出的無 API 端到端 gate。"""

import importlib
import json
from pathlib import Path

import pandas as pd
import pytest

from LLM_as_a_Judge.LLM_as_a_Judge import LLMAsAJudge
from LLM_as_a_Judge.evaluation_records import EvaluationLedger
from LLM_as_a_Judge.validation_sets import (
    EXPANSION_PURPOSES,
    GENERALIZATION_PURPOSES,
    TEMPLATE_COMPOSITE_1,
    TEMPLATE_EXPANSION_5,
    TEMPLATE_GENERALIZATION_5,
    TEMPLATE_MINIMAL_5,
    TEMPLATE_STRATIFIED_10,
    VALIDATION_PURPOSES,
)


evaluator_module = importlib.import_module("LLM_as_a_Judge.LLM_as_a_Judge")
ROOT = Path(__file__).parents[1]


CASES = (
    (
        1,
        {
            "answer_shape": "scalar",
            "presentation": ["text"],
            "explicitly_requested": False,
            "confidence": "high",
        },
        """value = float(df['value'].mean())
payload = {'label': '平均值', 'value': round(value, 2)}
template_output = render_output('text', payload)
""",
        0,
    ),
    (
        3,
        {
            "answer_shape": "records",
            "presentation": ["heatmap"],
            "explicitly_requested": True,
            "confidence": "high",
        },
        """payload = {'x': df['x'].tolist(), 'y': df['y'].tolist(), 'weights': None}
template_output = render_output('heatmap', payload, '二維熱區')
""",
        1,
    ),
    (
        9,
        {
            "answer_shape": "table",
            "presentation": ["table"],
            "explicitly_requested": False,
            "confidence": "high",
        },
        """rows = [['甲', 3, 1], ['乙', 2, 2]]
payload = {'columns': ['類別', '成功', '失敗'], 'rows': rows}
template_output = render_output('table', payload)
""",
        0,
    ),
    (
        14,
        {
            "answer_shape": "records",
            "presentation": ["pie"],
            "explicitly_requested": True,
            "confidence": "high",
        },
        """payload = {'series': [{'name': '比例', 'labels': ['甲', '乙'], 'values': [6, 4]}]}
template_output = render_output('pie', payload, '組成比例')
""",
        1,
    ),
    (
        80,
        {
            "answer_shape": "narrative",
            "presentation": ["text"],
            "explicitly_requested": False,
            "confidence": "high",
        },
        """mean_value = float(df['value'].mean())
payload = {'label': '綜合分析', 'value': f'平均值為 {mean_value:.1f}，應依數據調整策略'}
template_output = render_output('text', payload)
""",
        0,
    ),
    (
        13,
        {
            "answer_shape": "composite",
            "presentation": ["text", "table", "bar"],
            "explicitly_requested": False,
            "confidence": "high",
        },
        """total = int(df['value'].sum())
payload = {'items': [
    {'kind': 'text', 'title': '摘要', 'payload': {'label': '總和', 'value': total}},
    {'kind': 'table', 'title': '明細', 'payload': {'columns': ['類別', '值'], 'rows': [['甲', 3], ['乙', 7]]}},
    {'kind': 'bar', 'title': '分布', 'payload': {'series': [{'name': '值', 'labels': ['甲', '乙'], 'values': [3, 7]}]}},
]}
template_output = render_output('composite', payload)
""",
        1,
    ),
)


def _evaluator(tmp_path, question_id):
    evaluator = object.__new__(LLMAsAJudge)
    evaluator.mode = "test"
    evaluator.enable_step1 = True
    evaluator.enable_output_template_lab = True
    evaluator.skip_insight = True
    evaluator.gen_model = "offline-fake"
    evaluator.gen_client = object()
    evaluator.df = pd.DataFrame({
        "value": [1, 2, 3, 4],
        "x": [0.1, 0.2, 0.8, 0.9],
        "y": [0.2, 0.3, 0.7, 0.8],
    })
    evaluator._current_q_num = question_id
    evaluator.plots_dir = str(tmp_path)
    evaluator.data_schema_info = "schema"
    evaluator.column_definitions_info = "definitions"
    evaluator.court_place_info = "court"
    evaluator.step1_route_records = []
    evaluator.template_records = []
    evaluator.insight_records = []
    evaluator.ledger = EvaluationLedger()
    evaluator._build_system_prompt = lambda *args: "BASE"
    return evaluator


def _step1(contract):
    return {
        "enhanced_prompt": "離線 fixture 問題",
        "needs_court_info": False,
        "required_column_groups": [],
        "normalized_result": {"output_contract": contract},
        "output_contract_status": "valid",
        "output_contract_route": "renderer_candidate",
        "input_tokens": 5,
        "output_tokens": 3,
        "total_tokens": 8,
    }


def test_validation_sets_exist_in_question_and_reference_sources() -> None:
    question_lines = (
        ROOT / "LLM_as_a_Judge" / "評估問題_new.txt"
    ).read_text(encoding="utf-8").splitlines()
    question_ids = {
        int(line.split(":", 1)[0]) for line in question_lines if ":" in line
    }
    notebook = json.loads(
        (ROOT / "LLM_as_a_Judge" / "example_new.ipynb").read_text(
            encoding="utf-8"
        )
    )
    notebook_text = "\n".join(
        "".join(cell.get("source", [])) for cell in notebook["cells"]
    )

    for question_set in (
        TEMPLATE_MINIMAL_5,
        TEMPLATE_COMPOSITE_1,
        TEMPLATE_STRATIFIED_10,
        TEMPLATE_EXPANSION_5,
        TEMPLATE_GENERALIZATION_5,
    ):
        assert len(question_set) == len(set(question_set))
        assert set(question_set) <= question_ids
        assert all(f"{question_id}." in notebook_text for question_id in question_set)


def test_minimal_and_stratified_sets_cover_planned_output_families() -> None:
    inventory = json.loads(
        (ROOT / "tests" / "fixtures" / "phase3_output_inventory.json").read_text(
            encoding="utf-8"
        )
    )
    shape_for_question = {
        question_id: shape
        for shape, ids in inventory["primary_answer_shape"].items()
        for question_id in ids
    }

    assert {shape_for_question[q] for q in TEMPLATE_MINIMAL_5} == {
        "scalar", "records", "table", "narrative"
    }
    assert shape_for_question[TEMPLATE_COMPOSITE_1[0]] == "composite"
    assert set(TEMPLATE_MINIMAL_5) <= set(TEMPLATE_STRATIFIED_10)
    assert set(TEMPLATE_COMPOSITE_1) <= set(TEMPLATE_STRATIFIED_10)
    assert set(TEMPLATE_STRATIFIED_10) == set(VALIDATION_PURPOSES)


def test_expansion_set_is_new_bounded_and_fully_documented() -> None:
    assert len(TEMPLATE_EXPANSION_5) == 5
    assert len(set(TEMPLATE_EXPANSION_5)) == 5
    assert not set(TEMPLATE_EXPANSION_5) & set(TEMPLATE_STRATIFIED_10)
    assert set(TEMPLATE_EXPANSION_5) == set(EXPANSION_PURPOSES)


def test_generalization_set_is_new_bounded_and_fully_documented() -> None:
    prior_questions = set(TEMPLATE_STRATIFIED_10) | set(TEMPLATE_EXPANSION_5)

    assert len(TEMPLATE_GENERALIZATION_5) == 5
    assert len(set(TEMPLATE_GENERALIZATION_5)) == 5
    assert not set(TEMPLATE_GENERALIZATION_5) & prior_questions
    assert set(TEMPLATE_GENERALIZATION_5) == set(GENERALIZATION_PURPOSES)


@pytest.mark.parametrize(
    ("question_id", "contract", "code", "expected_figures"),
    CASES,
)
def test_six_output_families_pass_real_executor_without_api(
    question_id,
    contract,
    code,
    expected_figures,
    monkeypatch,
    tmp_path,
) -> None:
    evaluator = _evaluator(tmp_path, question_id)
    monkeypatch.setattr(
        evaluator_module,
        "run_prompt_enhancement",
        lambda *args, **kwargs: _step1(contract),
    )
    monkeypatch.setattr(
        evaluator_module,
        "run_code_generation",
        lambda *args, **kwargs: {
            "code": code,
            "input_tokens": 20,
            "output_tokens": 10,
            "total_tokens": 30,
        },
    )

    result = evaluator._run_pipeline("離線 fixture 問題")

    assert len(result[2]) == expected_figures
    assert evaluator.template_records[0]["actual_route"] == "renderer"
    assert evaluator.template_records[0]["fallback_reason"] == ""
    assert evaluator.ledger.usage_for_stage("repair")["calls"] == 0
    assert evaluator.ledger.questions[question_id].execution_success is True
