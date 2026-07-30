"""Phase 1：Step 1 場地資訊 routing 的純離線測試。"""

from types import SimpleNamespace

from config.prompts import create_enhancement_system_prompt
from LLM_as_a_Judge.LLM_as_a_Judge import LLMAsAJudge
from utils.analysis_workflow import run_prompt_enhancement


class _FakeCompletions:
    def __init__(self, content: str):
        self.content = content

    def create(self, **kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))],
            usage=SimpleNamespace(
                prompt_tokens=11,
                completion_tokens=7,
                total_tokens=18,
            ),
        )


def _fake_client(content: str):
    return SimpleNamespace(
        chat=SimpleNamespace(completions=_FakeCompletions(content))
    )


def _result(content: str, question: str):
    return run_prompt_enhancement(
        _fake_client(content),
        "fake-model",
        create_enhancement_system_prompt(),
        question,
        [],
    )


def test_enhancement_contract_requires_boolean_needs_court_info() -> None:
    prompt = create_enhancement_system_prompt()
    assert '"needs_court_info": true' in prompt
    assert "JSON 布林值" in prompt


def test_valid_llm_boolean_controls_non_spatial_route() -> None:
    content = """{
      "analysis_subject": "周天成",
      "analysis_unit": "單拍",
      "temporal_requirement": "無",
      "scoring_rule": "無",
      "spatial_requirement": "無",
      "needs_court_info": false,
      "is_related_to_previous_code": false,
      "required_column_groups": ["shot_type"]
    }"""
    result = _result(content, "周天成最常使用什麼球種？")
    assert result["needs_court_info"] is False
    assert result["needs_court_info_llm"] is False
    assert result["needs_court_info_source"] == "llm"
    assert result["raw_response"] == content
    assert result["normalized_result"]["needs_court_info"] is False


def test_high_confidence_spatial_semantics_prevent_false_negative() -> None:
    content = """{
      "analysis_subject": "周天成",
      "analysis_unit": "單拍",
      "temporal_requirement": "無",
      "scoring_rule": "Active Win",
      "spatial_requirement": "前中後場",
      "needs_court_info": false,
      "is_related_to_previous_code": false,
      "required_column_groups": ["player_location", "shot_type", "scoring_reason"]
    }"""
    result = _result(content, "當周天成站在前場時，他最主要的得分球種？")
    assert result["needs_court_info"] is True
    assert result["needs_court_info_llm"] is False
    assert result["semantic_court_signal"] is True
    assert result["needs_court_info_source"] == "semantic_guard"


def test_malformed_json_still_uses_generic_spatial_guard() -> None:
    result = _result("不是 JSON", "比較雙方在球場四角的落點分布")
    assert result["needs_court_info"] is True
    assert result["needs_court_info_llm"] is None
    assert result["needs_court_info_source"] == "semantic_guard"
    assert result["parse_error"]


def test_generic_region_word_is_covered_without_question_id_rule() -> None:
    result = _result("不是 JSON", "哪一個區域的主動得分最多？")

    assert result["needs_court_info"] is True
    assert result["needs_court_info_source"] == "semantic_guard"


def test_string_boolean_is_not_treated_as_truthy() -> None:
    content = """{
      "needs_court_info": "false",
      "is_related_to_previous_code": false,
      "required_column_groups": []
    }"""
    result = _result(content, "周天成最常使用什麼球種？")
    assert result["needs_court_info"] is False
    assert result["needs_court_info_llm"] is None
    assert result["needs_court_info_source"] == "default"
    assert "needs_court_info" in result["parse_error"]


def test_generic_location_words_do_not_force_formal_zone_metadata() -> None:
    content = """{
      "needs_court_info": false,
      "is_related_to_previous_code": false,
      "required_column_groups": ["coordinates"]
    }"""
    result = _result(content, "繪製殺球落點座標熱區圖")
    assert result["semantic_court_signal"] is False
    assert result["needs_court_info"] is False


def test_step1_trace_records_raw_normalized_and_actual_metadata() -> None:
    evaluator = object.__new__(LLMAsAJudge)
    evaluator.mode = "our_method"
    evaluator.enable_step1 = True
    evaluator.enable_output_template_lab = False
    evaluator.court_place_info = "完整場地定義"
    evaluator.step1_route_records = []
    evaluator._current_q_num = 10
    enhancement = {
        "raw_response": '{"needs_court_info": false}',
        "normalized_result": {"needs_court_info": True},
        "needs_court_info": True,
        "needs_court_info_llm": False,
        "needs_court_info_source": "semantic_guard",
        "semantic_court_signal": True,
        "parse_error": "",
    }

    evaluator._record_step1_route(
        enhancement,
        ["player_location", "shot_type"],
        needs_court_info=True,
    )

    trace = evaluator.step1_route_records[0]
    assert trace["question_id"] == 10
    assert trace["raw_response"] == '{"needs_court_info": false}'
    assert trace["normalized_result"]["needs_court_info"] is True
    assert trace["court_metadata_passed"] == "full_court_place"
    assert trace["output_contract"] is None
    notebook_summary = evaluator._step1_trace_markdown()
    assert "完整場地資訊" in notebook_summary
    assert "semantic_guard" in notebook_summary
    assert "raw_response" not in notebook_summary


def test_step1_trace_reports_no_metadata_when_gate_is_false() -> None:
    evaluator = object.__new__(LLMAsAJudge)
    evaluator.mode = "test"
    evaluator.enable_step1 = True
    evaluator.enable_output_template_lab = True
    evaluator.court_place_info = "完整場地定義"
    evaluator.step1_route_records = []
    evaluator._current_q_num = 3

    evaluator._record_step1_route(None, [], needs_court_info=False)

    assert evaluator.step1_route_records[0]["court_metadata_passed"] == "none"
    assert evaluator.step1_route_records[0]["output_contract"] is None
