"""Phase 3 的 test-only 輸出型態合約。

本模組只描述呈現形式，不得承載分析主體、篩選條件、統計分母或圖表參數。
"""

from dataclasses import asdict, dataclass
from typing import Any, Optional


ANSWER_SHAPES = ("scalar", "records", "table", "narrative", "composite")
PRESENTATIONS = ("text", "table", "bar", "pie", "line", "scatter", "heatmap")
CONFIDENCE_LEVELS = ("high", "medium", "low")
OUTPUT_CONTRACT_REQUIRED_KEYS = {
    "answer_shape",
    "presentation",
    "confidence",
}
OUTPUT_CONTRACT_OPTIONAL_KEYS = {"explicitly_requested"}
OUTPUT_CONTRACT_KEYS = OUTPUT_CONTRACT_REQUIRED_KEYS | OUTPUT_CONTRACT_OPTIONAL_KEYS


@dataclass(frozen=True)
class OutputContract:
    """已通過白名單驗證的輸出型態預測。"""

    answer_shape: str
    presentation: tuple[str, ...]
    confidence: str
    explicitly_requested: Optional[bool] = None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["presentation"] = list(self.presentation)
        if self.explicitly_requested is None:
            result.pop("explicitly_requested")
        return result


@dataclass(frozen=True)
class OutputContractValidation:
    """驗證結果；失敗或低信心都不要求額外 LLM 呼叫。"""

    status: str
    route: str
    contract: Optional[OutputContract]
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "route": self.route,
            "contract": self.contract.to_dict() if self.contract else None,
            "errors": list(self.errors),
        }


def validate_output_contract(value: Any) -> dict[str, Any]:
    """用小型 enum 白名單驗證合約，不猜測或修補模型輸出。"""

    errors = []
    if not isinstance(value, dict):
        return OutputContractValidation(
            "invalid",
            "existing_free_code",
            None,
            ("output_contract 必須是 JSON object",),
        ).to_dict()

    missing = sorted(OUTPUT_CONTRACT_REQUIRED_KEYS - set(value))
    extra = sorted(set(value) - OUTPUT_CONTRACT_KEYS)
    if missing:
        errors.append(f"缺少欄位: {', '.join(missing)}")
    if extra:
        errors.append(f"不允許額外欄位: {', '.join(extra)}")

    answer_shape = value.get("answer_shape")
    if answer_shape not in ANSWER_SHAPES:
        errors.append("answer_shape 不在白名單")

    presentation = value.get("presentation")
    if not isinstance(presentation, list) or not presentation:
        errors.append("presentation 必須是非空 JSON array")
        presentation_values = ()
    else:
        presentation_values = tuple(presentation)
        all_strings = all(
            isinstance(item, str) for item in presentation_values
        )
        if not all_strings:
            errors.append("presentation 只能包含字串 enum")
        else:
            if any(item not in PRESENTATIONS for item in presentation_values):
                errors.append("presentation 含有白名單外的值")
            if len(set(presentation_values)) != len(presentation_values):
                errors.append("presentation 不可包含重複值")
        if len(presentation_values) > 3:
            errors.append("presentation 最多三種，避免無限制產物")

    explicitly_requested = value.get("explicitly_requested")
    if (
        "explicitly_requested" in value
        and type(explicitly_requested) is not bool
    ):
        errors.append("explicitly_requested 必須是 JSON boolean")

    confidence = value.get("confidence")
    if confidence not in CONFIDENCE_LEVELS:
        errors.append("confidence 不在白名單")

    if errors:
        return OutputContractValidation(
            "invalid", "existing_free_code", None, tuple(errors)
        ).to_dict()

    contract = OutputContract(
        answer_shape,
        presentation_values,
        confidence,
        explicitly_requested,
    )
    route = "existing_free_code" if confidence == "low" else "renderer_candidate"
    return OutputContractValidation("valid", route, contract).to_dict()
