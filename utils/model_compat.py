"""集中處理不同模型的 Chat Completions 參數相容性。"""

from __future__ import annotations


def supports_custom_temperature(model: str) -> bool:
    """回傳模型是否接受非預設 temperature。

    GPT-5 系列目前只接受預設值；省略參數比明傳 ``1`` 更能保留
    供應端預設行為。其他既有模型則維持原本的 temperature 設定。
    """

    normalized = str(model).strip().lower()
    is_gpt5_family = (
        normalized == "gpt-5"
        or normalized.startswith("gpt-5-")
        or normalized.startswith("gpt-5.")
    )
    return not is_gpt5_family


def temperature_kwargs(model: str, temperature: float) -> dict[str, float]:
    """建立可安全展開到 Chat Completions 的 temperature 參數。"""

    if supports_custom_temperature(model):
        return {"temperature": temperature}
    return {}
