"""Phase 5：只供 test mode 延遲載入的呈現 adapter。"""

import ast
from dataclasses import dataclass
from typing import Any

import matplotlib.pyplot as plt

from LLM_as_a_Judge.test_output_runtime import (
    ChartSeries,
    CompositeItem,
    CompositeResult,
    HeatmapPoints,
    RecordResult,
    ScalarResult,
    TableResult,
    render_bar,
    render_composite,
    render_heatmap,
    render_line,
    render_pie,
    render_scatter,
    render_table,
    render_text,
)


_RENDERERS = {
    "text": render_text,
    "table": render_table,
    "bar": render_bar,
    "pie": render_pie,
    "line": render_line,
    "scatter": render_scatter,
    "heatmap": render_heatmap,
    "composite": render_composite,
}
_PRESENTATION_CALLS = {
    "ScalarResult",
    "RecordResult",
    "TableResult",
    "ChartSeries",
    "HeatmapPoints",
    "CompositeItem",
    "CompositeResult",
    "render_output",
}


@dataclass
class TemplateExecutionContext:
    """test mode 單題所需 prompt、預載 globals 與可變追蹤紀錄。"""

    system_prompt: str
    extended_globals: dict[str, Any]
    report: dict[str, Any]


def _fallback_text(payload) -> str:
    """renderer 失敗時保留資料結果，不自行補分析條件。"""

    if isinstance(payload, (ScalarResult, RecordResult, TableResult, str)):
        return render_text(payload)
    if isinstance(payload, ChartSeries):
        rows = list(zip(payload.labels, payload.values))
        return render_text(TableResult(["label", payload.name or "value"], rows))
    if isinstance(payload, (list, tuple)) and all(
        isinstance(item, ChartSeries) for item in payload
    ):
        lines = []
        for item in payload:
            lines.append(f"[{item.name}]")
            lines.extend(
                f"{label}: {value}"
                for label, value in zip(item.labels, item.values)
            )
        return "\n".join(lines) or "無資料"
    if isinstance(payload, HeatmapPoints):
        return f"二維資料點數: {len(payload.x)}"
    if isinstance(payload, CompositeResult):
        sections = []
        for item in payload.items:
            try:
                sections.append(_fallback_text(item.payload))
            except (TypeError, ValueError):
                sections.append(f"{item.title or item.kind}: 無法轉為文字")
        return "\n\n".join(sections)
    if isinstance(payload, dict):
        if "label" in payload and "value" in payload:
            return f"{payload.get('label')}: {payload.get('value')}"
        if "columns" in payload and "rows" in payload:
            try:
                return render_text(TableResult(
                    payload["columns"], payload["rows"]
                ))
            except (TypeError, ValueError):
                return f"表格資料列數: {len(payload.get('rows', []))}"
        if "series" in payload:
            lines = []
            for series in payload.get("series", []):
                if not isinstance(series, dict):
                    continue
                lines.append(f"[{series.get('name', 'value')}]")
                lines.extend(
                    f"{label}: {value}"
                    for label, value in zip(
                        series.get("labels", []),
                        series.get("values", []),
                    )
                )
            return "\n".join(lines) or "無資料"
        if "x" in payload and "y" in payload:
            return f"二維資料點數: {min(len(payload.get('x', [])), len(payload.get('y', [])))}"
        if "items" in payload:
            return "\n\n".join(
                _fallback_text(item.get("payload"))
                for item in payload.get("items", [])
                if isinstance(item, dict)
            ) or "無資料"
    return "呈現模板失敗；分析程式已完成，但 payload 無法安全轉為文字。"


def _coerce_series(payload):
    if isinstance(payload, ChartSeries):
        return payload
    if isinstance(payload, dict) and "series" in payload:
        payload = payload["series"]
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, (list, tuple)):
        raise TypeError("chart payload 必須包含 series")
    result = []
    for item in payload:
        if isinstance(item, ChartSeries):
            result.append(item)
        elif isinstance(item, dict):
            missing = {"labels", "values"} - set(item)
            if missing:
                raise ValueError(
                    "series 缺少必要欄位: " + ", ".join(sorted(missing))
                )
            result.append(ChartSeries(
                item.get("name", "value"),
                item["labels"],
                item["values"],
            ))
        else:
            raise TypeError("series item 必須是 object")
    return result[0] if len(result) == 1 else result


def _coerce_payload(kind, payload):
    """把短小 JSON-like payload 轉成 Phase 4 型別，驗證留在 facade 內。"""

    if kind == "text":
        if isinstance(payload, (ScalarResult, RecordResult, TableResult, str)):
            return payload
        if isinstance(payload, dict):
            missing = {"label", "value"} - set(payload)
            if missing:
                raise ValueError(
                    "text payload 缺少必要欄位: "
                    + ", ".join(sorted(missing))
                )
            return ScalarResult(
                payload["label"],
                payload["value"],
                payload.get("unit", ""),
                payload.get("note", ""),
            )
        return payload
    if kind == "table":
        if isinstance(payload, (RecordResult, TableResult)):
            return payload
        if isinstance(payload, dict) and "records" in payload:
            return RecordResult(
                payload["records"],
                payload.get("columns", ()),
                payload.get("title", ""),
            )
        if isinstance(payload, dict):
            missing = {"columns", "rows"} - set(payload)
            if missing:
                raise ValueError(
                    "table payload 缺少必要欄位: "
                    + ", ".join(sorted(missing))
                )
            return TableResult(
                payload["columns"],
                payload["rows"],
                payload.get("title", ""),
            )
        return payload
    if kind in {"bar", "pie", "line", "scatter"}:
        return _coerce_series(payload)
    if kind == "heatmap":
        if isinstance(payload, HeatmapPoints):
            return payload
        if isinstance(payload, dict):
            missing = {"x", "y"} - set(payload)
            if missing:
                raise ValueError(
                    "heatmap payload 缺少必要欄位: "
                    + ", ".join(sorted(missing))
                )
            return HeatmapPoints(
                payload["x"],
                payload["y"],
                payload.get("weights"),
            )
        return payload
    if kind == "composite":
        if isinstance(payload, CompositeResult):
            return payload
        if not isinstance(payload, dict):
            return payload
        if "items" not in payload:
            raise ValueError("composite payload 缺少必要欄位: items")
        items = []
        for item in payload.get("items", []):
            if not isinstance(item, dict):
                raise TypeError("composite item 必須是 object")
            item_kind = item.get("kind")
            items.append(CompositeItem(
                item_kind,
                _coerce_payload(item_kind, item.get("payload")),
                item.get("title", ""),
            ))
        return CompositeResult(items)
    return payload


def _normalize_single_wrapper(kind, payload):
    """接受唯一明確的 `{kind: payload}` 冗餘包裝，不猜測內容。"""

    if (
        isinstance(payload, dict)
        and set(payload) == {kind}
        and isinstance(payload[kind], (dict, list, tuple))
    ):
        return payload[kind], True
    return payload, False


def _payload_has_data(kind, payload):
    """判斷受限 payload 是否有可呈現資料，不分析題意。"""

    if kind == "text":
        if isinstance(payload, ScalarResult):
            return payload.value is not None
        if isinstance(payload, RecordResult):
            return bool(payload.records)
        if isinstance(payload, TableResult):
            return bool(payload.rows)
        return bool(str(payload))
    if kind == "table":
        if isinstance(payload, RecordResult):
            return bool(payload.records)
        if isinstance(payload, TableResult):
            return bool(payload.rows)
    if kind in {"bar", "line", "scatter"}:
        items = payload if isinstance(payload, (list, tuple)) else (payload,)
        return any(bool(item.values) for item in items)
    if kind == "pie":
        items = payload if isinstance(payload, (list, tuple)) else (payload,)
        return bool(items) and any(
            bool(item.values) and sum(item.values) > 0 for item in items
        )
    if kind == "heatmap":
        return bool(payload.x)
    if kind == "composite":
        return any(
            _payload_has_data(item.kind, item.payload)
            for item in payload.items
        )
    return False


def _artifact_has_content(kind, artifact, payload_nonempty):
    """以 Matplotlib artist 驗證非空 payload 沒有產生空白 Figure。"""

    if not payload_nonempty:
        return False
    if kind in {"text", "table"}:
        return True
    if artifact is None or not hasattr(artifact, "axes"):
        return False
    return any(
        ax.lines
        or ax.patches
        or ax.collections
        or ax.images
        or ax.tables
        or ax.texts
        for ax in artifact.axes
    )


def _render_and_emit(kind, payload, title):
    renderer = _RENDERERS[kind]
    if kind in {"bar", "pie", "line", "scatter", "heatmap"}:
        artifact = renderer(payload, title=title)
    else:
        artifact = renderer(payload)
    if kind == "text":
        print(artifact)
    elif kind == "table":
        print(artifact.to_string(index=False) if not artifact.empty else "無資料")
    return artifact


def _make_render_output(contract, report):
    expected = set(contract.get("presentation", []))
    allows_composite = (
        contract.get("answer_shape") == "composite" or len(expected) > 1
    )

    def render_output(kind, payload, title=""):
        """受限呈現入口；任何 renderer 錯誤皆轉為文字，不觸發 repair。"""

        report["renderer_calls"] += 1
        report["attempted"] = True
        figures_before = set(plt.get_fignums())
        if report["renderer_calls"] > 1:
            reason = "render_output 每題只能呼叫一次；多輸出請使用 composite"
            report.update({
                "actual_route": "generic_text_fallback",
                "renderer_status": "fallback",
                "fallback_reason": reason,
            })
            text = _fallback_text(payload)
            print(text)
            return text

        try:
            if not isinstance(title, str) or len(title) > 120:
                raise ValueError("title 必須是 120 字以內字串")
            if kind not in _RENDERERS:
                raise ValueError("presentation kind 不在白名單")
            if kind == "composite":
                if not allows_composite:
                    raise ValueError("輸出合約未允許 composite")
            elif kind not in expected:
                raise ValueError("presentation kind 與 Step 1 合約不一致")
            payload, normalized = _normalize_single_wrapper(kind, payload)
            report["payload_normalized"] = normalized
            typed_payload = _coerce_payload(kind, payload)
            if kind == "composite" and any(
                item.kind not in expected for item in typed_payload.items
            ):
                raise ValueError("composite item 與 Step 1 合約不一致")
            artifact = _render_and_emit(kind, typed_payload, title)
            payload_nonempty = _payload_has_data(kind, typed_payload)
            artifact_nonempty = _artifact_has_content(
                kind,
                artifact,
                payload_nonempty,
            )
            if payload_nonempty and not artifact_nonempty:
                raise ValueError("非空 payload 未產生可見 artifact")
            report.update({
                "actual_route": "renderer",
                "renderer_status": (
                    "completed" if artifact_nonempty else "empty"
                ),
                "presentation_used": kind,
                "payload_normalized": normalized,
                "artifact_nonempty": artifact_nonempty,
                "fallback_reason": "",
            })
            return artifact
        except Exception as error:
            for figure_number in set(plt.get_fignums()) - figures_before:
                plt.close(figure_number)
            reason = f"{type(error).__name__}: {error}"
            report.update({
                "actual_route": "generic_text_fallback",
                "renderer_status": "fallback",
                "presentation_used": "text",
                "artifact_nonempty": False,
                "fallback_reason": reason,
            })
            text = _fallback_text(payload)
            print(text)
            return text

    return render_output


def _test_rendering_instruction(contract) -> str:
    selected = tuple(contract.get("presentation", [])) or ("text",)
    presentations = ", ".join(selected)
    format_rules = {
        "text": 'text={"label": str, "value": scalar, "unit": str, "note": str}',
        "table": 'table={"columns": [...], "rows": [[...], ...]}',
        "bar": 'bar={"series": [{"name": str, "labels": 分類, "values": 數值}]}；最多6個series且共用labels',
        "pie": 'pie={"series": [{"name": str, "labels": 分類, "values": 非負數值}]}；只能1個series',
        "line": 'line={"series": [{"name": str, "labels": 有序X分類, "values": Y數值}]}；最多12個series且共用labels',
        "scatter": 'scatter={"series": [{"name": str, "labels": X數值, "values": Y數值}]}；X/Y等長，最多12個series',
        "heatmap": 'heatmap={"x": X數值, "y": Y數值, "weights": 非負數值或None}；三者等長，最多10000點',
    }
    payload_lines = [format_rules[kind] for kind in selected]
    if contract.get("answer_shape") == "composite" or len(selected) > 1:
        payload_lines.append(
            'composite={"items": [{"kind": kind, "payload": 上述格式, "title": str}]}；最多4個items'
        )
    payload_rules = "\n  ".join(payload_lines)
    return f"""

**test mode 受限呈現規範（不改變分析邏輯）**
- 本段取代上方關於自行繪圖、`fig` 與重複 `print()` 的規則；其他資料分析規則仍適用。
- 本題輸出合約：answer_shape={contract.get('answer_shape')}；presentation=[{presentations}]。
- 資料篩選、欄位、分母、Top-K 與統計條件仍依原題及 metadata 決定；不得由輸出形式反推分析規則。
- 計算比例／率時，先建立題意指定的完整母體再定義事件分子；除非題意明確要求條件比例，不可先用結果欄位縮小分母。
- 主動得分限擊球／球種直接得分；回合情境得分依最終 getpoint_player，不限最後擊球者。
- 當目標統計單位不同於原始資料列時，先彙整成每個目標單位一列再計數；不可把群組結果在原始列上重複加總。
- Step 2 只輸出可驗證的計算、統計證據與限制；即使題目詢問原因、策略或建議，也交由 Step 4 洞察處理，不可寫入程式輸出或 payload note。
- answer_shape=narrative 時，Step 2 仍只呈現供 Step 4 使用的 evidence text／table，不直接撰寫最終建議。
- 執行環境只預載 `render_output(kind, payload, title='')`；不要 import 本專案 runtime，也不要 import 或呼叫 matplotlib／seaborn。
- 完成分析後建立短小 dict payload，並且只呼叫一次 `template_output = render_output(...)`：
  {payload_rules}
- 單一輸出 kind 使用 text/table/bar/pie/line/scatter/heatmap；合約有多種呈現或 answer_shape=composite 時，用 composite payload 並呼叫 kind='composite'。
- text／narrative 不得被強迫轉成圖表。render_output 會負責 print、空資料與圖表樣式，不要自行重複繪圖或字體程式碼。
"""


def prepare_template_execution(base_system_prompt, enhancement_result):
    """依 Phase 3 合約建立 test mode context；不進行任何 LLM 呼叫。"""

    enhancement_result = enhancement_result or {}
    normalized = enhancement_result.get("normalized_result", {})
    contract = normalized.get("output_contract")
    status = enhancement_result.get("output_contract_status", "invalid")
    planned_route = enhancement_result.get(
        "output_contract_route", "existing_free_code"
    )
    enabled = (
        status == "valid"
        and planned_route == "renderer_candidate"
        and isinstance(contract, dict)
    )
    report = {
        "enabled": enabled,
        "contract": contract,
        "contract_status": status,
        "planned_route": planned_route,
        "attempted": False,
        "renderer_calls": 0,
        "renderer_status": "not_started" if enabled else "skipped",
        "actual_route": "pending" if enabled else "existing_free_code",
        "presentation_used": "",
        "payload_normalized": False,
        "artifact_nonempty": None,
        "requires_insight": bool(
            isinstance(contract, dict)
            and contract.get("answer_shape") == "narrative"
        ),
        "fallback_reason": (
            "" if enabled else f"contract_{status}_{planned_route}"
        ),
    }
    if not enabled:
        return TemplateExecutionContext(base_system_prompt, {}, report)

    extended_globals = {
        "render_output": _make_render_output(contract, report),
    }
    return TemplateExecutionContext(
        base_system_prompt + _test_rendering_instruction(contract),
        extended_globals,
        report,
    )


def finalize_template_report(report):
    """模型未呼叫 renderer 時記為既有自由呈現，不額外 repair。"""

    if report.get("enabled") and not report.get("attempted"):
        report.update({
            "actual_route": "existing_free_code",
            "renderer_status": "fallback",
            "fallback_reason": "render_output_not_called",
        })
    return report


def estimate_code_token_split(code, total_output_tokens):
    """按 AST 行範圍估算分析／呈現 output token；只作分帳估計。"""

    total_output_tokens = int(total_output_tokens or 0)
    if not code or total_output_tokens <= 0:
        return {
            "analysis_output_tokens_estimated": total_output_tokens,
            "presentation_output_tokens_estimated": 0,
        }
    lines = code.splitlines(keepends=True)
    presentation_lines = set()
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = (
                    node.targets
                    if isinstance(node, ast.Assign)
                    else [node.target]
                )
                names = [
                    target.id for target in targets
                    if isinstance(target, ast.Name)
                ]
                if any(
                    "payload" in name or name == "template_output"
                    for name in names
                ):
                    start = max(int(getattr(node, "lineno", 1)) - 1, 0)
                    end = int(getattr(node, "end_lineno", start + 1))
                    presentation_lines.update(range(start, end))
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            name = function.id if isinstance(function, ast.Name) else ""
            if name in _PRESENTATION_CALLS:
                start = max(int(getattr(node, "lineno", 1)) - 1, 0)
                end = int(getattr(node, "end_lineno", start + 1))
                presentation_lines.update(range(start, end))
    except SyntaxError:
        presentation_lines = {
            index for index, line in enumerate(lines)
            if any(marker in line for marker in _PRESENTATION_CALLS)
        }
    total_chars = sum(len(line.strip()) for line in lines)
    presentation_chars = sum(
        len(lines[index].strip())
        for index in presentation_lines
        if index < len(lines)
    )
    if total_chars <= 0:
        presentation_tokens = 0
    else:
        presentation_tokens = round(
            total_output_tokens * presentation_chars / total_chars
        )
    presentation_tokens = max(0, min(total_output_tokens, presentation_tokens))
    return {
        "analysis_output_tokens_estimated": (
            total_output_tokens - presentation_tokens
        ),
        "presentation_output_tokens_estimated": presentation_tokens,
    }


def estimate_prompt_token_split(
    base_system_prompt,
    final_system_prompt,
    enhanced_prompt,
    total_input_tokens,
):
    """按 prompt 字元比例估算 Step 2 分析／呈現 input token。"""

    total_input_tokens = int(total_input_tokens or 0)
    presentation_chars = max(
        len(final_system_prompt) - len(base_system_prompt),
        0,
    )
    analysis_chars = len(base_system_prompt) + len(enhanced_prompt or "")
    total_chars = analysis_chars + presentation_chars
    if total_chars <= 0 or total_input_tokens <= 0:
        presentation_tokens = 0
    else:
        presentation_tokens = round(
            total_input_tokens * presentation_chars / total_chars
        )
    presentation_tokens = max(0, min(total_input_tokens, presentation_tokens))
    return {
        "analysis_input_tokens_estimated": (
            total_input_tokens - presentation_tokens
        ),
        "presentation_input_tokens_estimated": presentation_tokens,
    }
