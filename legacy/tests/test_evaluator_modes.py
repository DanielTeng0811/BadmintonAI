"""評估模式設定的純離線回歸測試。"""

import pytest

from LLM_as_a_Judge.mode_config import (
    SUPPORTED_MODES,
    TEST_MODE,
    enables_output_template_lab,
    get_mode_label,
    get_mode_profile,
    resolve_enable_step1,
    validate_evaluator_mode,
)


def test_supported_modes_remove_experimental_and_add_test() -> None:
    assert SUPPORTED_MODES == (
        "baseline_minimal",
        "baseline_metadata",
        "baseline_fullprompt",
        "our_method",
        "test",
    )
    assert "experimental_template" not in SUPPORTED_MODES


@pytest.mark.parametrize("mode", SUPPORTED_MODES)
def test_supported_modes_are_valid(mode: str) -> None:
    validate_evaluator_mode(mode)


def test_removed_experimental_mode_is_rejected() -> None:
    with pytest.raises(ValueError, match="不支援的模式"):
        validate_evaluator_mode("experimental_template")


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("baseline_minimal", False),
        ("baseline_metadata", False),
        ("baseline_fullprompt", False),
        ("our_method", True),
        (TEST_MODE, True),
    ],
)
def test_step1_defaults(mode: str, expected: bool) -> None:
    assert resolve_enable_step1(mode) is expected


def test_step1_override_is_respected() -> None:
    assert resolve_enable_step1(TEST_MODE, False) is False
    assert resolve_enable_step1("baseline_minimal", True) is True


def test_test_mode_has_distinct_label() -> None:
    assert get_mode_label(TEST_MODE) == "隔離測試模式 test"


@pytest.mark.parametrize(
    "mode",
    [
        "baseline_minimal",
        "baseline_metadata",
        "baseline_fullprompt",
        "our_method",
    ],
)
def test_output_template_lab_is_disabled_for_existing_modes(mode: str) -> None:
    assert enables_output_template_lab(mode) is False


def test_output_template_lab_is_enabled_only_for_test_mode() -> None:
    assert enables_output_template_lab(TEST_MODE) is True


@pytest.mark.parametrize("mode", SUPPORTED_MODES)
def test_mode_profile_matches_legacy_helpers(mode: str) -> None:
    profile = get_mode_profile(mode)

    assert profile.label == get_mode_label(mode)
    assert profile.enable_step1 == resolve_enable_step1(mode)
    assert profile.output_template_lab == enables_output_template_lab(mode)
