"""test mode 與既有模式隔離的純離線測試。"""

import importlib

from LLM_as_a_Judge.LLM_as_a_Judge import LLMAsAJudge
from LLM_as_a_Judge.mode_config import TEST_MODE


def _evaluator_without_api(mode: str):
    evaluator = object.__new__(LLMAsAJudge)
    evaluator.mode = mode
    evaluator.data_schema_info = "完整 schema"
    evaluator.column_definitions_info = "完整欄位定義"
    evaluator.court_place_info = "完整場地定義"
    return evaluator


def test_test_mode_uses_step1_filtered_prompt_without_changing_our_method(
    monkeypatch,
) -> None:
    calls = []

    def fake_filter(groups, schema, definitions):
        calls.append((groups, schema, definitions))
        return "篩選 schema", "篩選欄位定義"

    monkeypatch.setattr(
        "LLM_as_a_Judge.LLM_as_a_Judge.filter_schema_and_definitions",
        fake_filter,
    )
    test_evaluator = _evaluator_without_api(TEST_MODE)
    our_evaluator = _evaluator_without_api("our_method")

    test_prompt = test_evaluator._build_system_prompt(["shot_type"], True)
    our_prompt = our_evaluator._build_system_prompt(["shot_type"], True)

    assert calls == [
        (["shot_type"], "完整 schema", "完整欄位定義"),
        (["shot_type"], "完整 schema", "完整欄位定義"),
    ]
    assert "篩選 schema" in test_prompt
    assert "完整場地定義" in test_prompt
    assert test_prompt == our_prompt


def test_test_mode_respects_current_court_info_gate(monkeypatch) -> None:
    monkeypatch.setattr(
        "LLM_as_a_Judge.LLM_as_a_Judge.filter_schema_and_definitions",
        lambda *args: ("篩選 schema", "篩選欄位定義"),
    )
    evaluator = _evaluator_without_api(TEST_MODE)

    prompt = evaluator._build_system_prompt(["shot_type"], False)

    assert "完整場地定義" not in prompt


def test_test_mode_passes_full_court_metadata_and_priority_rule(monkeypatch) -> None:
    full_court_info = "完整場地定義\nZones 1-24\n不可裁切的尾端標記"
    monkeypatch.setattr(
        "LLM_as_a_Judge.LLM_as_a_Judge.filter_schema_and_definitions",
        lambda *args: ("篩選 schema", "篩選欄位定義"),
    )
    evaluator = _evaluator_without_api(TEST_MODE)
    evaluator.court_place_info = full_court_info
    prompt = evaluator._build_system_prompt(["player_location"], True)
    assert full_court_info in prompt
    assert "已有正式場地定義時" in prompt
    assert "分位數" in prompt


def test_metadata_priority_rule_does_not_change_fullprompt_baseline() -> None:
    evaluator = _evaluator_without_api("baseline_fullprompt")
    prompt = evaluator._build_system_prompt([], True)
    assert "完整場地定義" in prompt
    assert "已有正式場地定義時" not in prompt


def test_test_mode_constructor_is_executable_without_experimental_dependencies(
    monkeypatch,
) -> None:
    evaluator_module = importlib.import_module(
        "LLM_as_a_Judge.LLM_as_a_Judge"
    )
    client_calls = []
    monkeypatch.setattr(evaluator_module, "load_dotenv", lambda **kwargs: None)
    monkeypatch.setattr(evaluator_module.os, "getenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        evaluator_module,
        "initialize_client",
        lambda *args, **kwargs: client_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(
        evaluator_module,
        "load_all_data",
        lambda: (object(), "schema", "definitions"),
    )
    monkeypatch.setattr(evaluator_module.os, "makedirs", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        LLMAsAJudge,
        "_load_reference_answers_with_duplicates",
        lambda self: {},
    )

    evaluator = LLMAsAJudge(mode=TEST_MODE)

    assert evaluator.mode == TEST_MODE
    assert evaluator.enable_step1 is True
    assert evaluator.enable_output_template_lab is True
    assert "test_run_" in evaluator.run_dir
    assert evaluator.gen_client is None
    assert evaluator.judge_client is None
    assert client_calls == []


def test_lazy_clients_only_initialize_requested_role(monkeypatch) -> None:
    evaluator_module = importlib.import_module(
        "LLM_as_a_Judge.LLM_as_a_Judge"
    )
    evaluator = object.__new__(LLMAsAJudge)
    evaluator.gen_api_mode = "OpenAI 官方"
    evaluator.judge_api_mode = "OpenAI 官方"
    evaluator.gen_client = None
    evaluator.judge_client = None
    evaluator._env_loaded = False
    calls = []
    monkeypatch.setattr(evaluator_module, "load_dotenv", lambda **kwargs: None)
    monkeypatch.setattr(
        evaluator_module.os,
        "getenv",
        lambda name: f"fake:{name}",
    )
    monkeypatch.setattr(
        evaluator_module,
        "initialize_client",
        lambda mode, key: calls.append((mode, key)) or object(),
    )

    first = evaluator._get_gen_client()
    second = evaluator._get_gen_client()

    assert first is second
    assert calls == [("OpenAI 官方", "fake:OPENAI_API_KEY")]
    assert evaluator.judge_client is None
