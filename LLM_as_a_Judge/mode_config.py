"""評估模式的純設定與驗證，不初始化任何 API client。"""

from dataclasses import dataclass


CORE_MODES = (
    "baseline_minimal",
    "baseline_metadata",
    "baseline_fullprompt",
    "our_method",
)
TEST_MODE = "test"
SUPPORTED_MODES = (*CORE_MODES, TEST_MODE)


@dataclass(frozen=True)
class ModeProfile:
    """集中描述 mode 差異，不承載或合併 prompt 內容。"""

    label: str
    prompt_kind: str
    enable_step1: bool
    metadata_policy: str
    output_template_lab: bool = False


MODE_PROFILES = {
    "baseline_minimal": ModeProfile(
        label="第一層 baseline_minimal",
        prompt_kind="minimal",
        enable_step1=False,
        metadata_policy="none",
    ),
    "baseline_metadata": ModeProfile(
        label="第二層 baseline_metadata",
        prompt_kind="metadata",
        enable_step1=False,
        metadata_policy="full",
    ),
    "baseline_fullprompt": ModeProfile(
        label="第三層 baseline_fullprompt",
        prompt_kind="full",
        enable_step1=False,
        metadata_policy="full",
    ),
    "our_method": ModeProfile(
        label="第四層 our_method",
        prompt_kind="filtered_full",
        enable_step1=True,
        metadata_policy="conditional_full",
    ),
    TEST_MODE: ModeProfile(
        label="隔離測試模式 test",
        prompt_kind="filtered_full",
        enable_step1=True,
        metadata_policy="conditional_full",
        output_template_lab=True,
    ),
}


def get_mode_profile(mode: str) -> ModeProfile:
    validate_evaluator_mode(mode)
    return MODE_PROFILES[mode]


def validate_evaluator_mode(mode: str) -> None:
    """拒絕未知或已移除的模式。"""

    if mode not in SUPPORTED_MODES:
        supported = ", ".join(SUPPORTED_MODES)
        raise ValueError(f"不支援的模式: {mode}；可用模式: {supported}")


def resolve_enable_step1(mode: str, override=None) -> bool:
    """正式方法與隔離測試模式預設啟用 Step 1。"""

    if override is not None:
        return bool(override)
    return get_mode_profile(mode).enable_step1


def get_mode_label(mode: str) -> str:
    """取得報表使用的模式名稱。"""

    return get_mode_profile(mode).label


def enables_output_template_lab(mode: str) -> bool:
    """新輸出模板只能在隔離 test mode 中開發與啟用。"""

    return get_mode_profile(mode).output_template_lab
