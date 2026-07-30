"""模型 API 參數相容性的純離線測試。"""

from types import SimpleNamespace

import pytest

from utils import analysis_workflow
from utils.model_compat import supports_custom_temperature, temperature_kwargs


@pytest.mark.parametrize(
    "model",
    [
        "gpt-5",
        "gpt-5-mini",
        "gpt-5-nano",
        "gpt-5-mini-2025-08-07",
        "gpt-5.6-luna",
        "gpt-5.6-terra",
        "gpt-5.6-sol",
    ],
)
def test_gpt5_family_uses_provider_default_temperature(model: str) -> None:
    assert supports_custom_temperature(model) is False
    assert temperature_kwargs(model, 0.0) == {}


@pytest.mark.parametrize(
    "model",
    ["gpt-4o-mini", "test-model", "claude-test", "gpt-50-test"],
)
def test_other_models_keep_requested_temperature(model: str) -> None:
    assert supports_custom_temperature(model) is True
    assert temperature_kwargs(model, 0.4) == {"temperature": 0.4}


class _Completions:
    def __init__(self) -> None:
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="洞察"))],
            usage=SimpleNamespace(prompt_tokens=2, completion_tokens=1),
        )


def _fake_client():
    completions = _Completions()
    return SimpleNamespace(
        chat=SimpleNamespace(completions=completions),
        recorded=completions,
    )


def test_insight_generation_omits_temperature_for_gpt5(monkeypatch) -> None:
    monkeypatch.setattr(analysis_workflow, "log_llm_interaction", lambda *args: None)
    client = _fake_client()

    result = analysis_workflow.run_insight_generation(
        client, "gpt-5-mini", "system", "prompt"
    )

    assert "temperature" not in client.recorded.calls[0]
    assert result["insight"] == "洞察"


def test_insight_generation_keeps_temperature_for_gpt4o_mini(monkeypatch) -> None:
    monkeypatch.setattr(analysis_workflow, "log_llm_interaction", lambda *args: None)
    client = _fake_client()

    analysis_workflow.run_insight_generation(client, "gpt-4o-mini", "system", "prompt")

    assert client.recorded.calls[0]["temperature"] == 0.4
