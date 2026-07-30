import matplotlib
matplotlib.use('Agg')  # 使用非互動式後端，不會彈出圖表視窗
import os
import sys
import json
import io
import platform
import re
from datetime import datetime
from dotenv import load_dotenv
import pandas as pd
import matplotlib.pyplot as plt
plt.show = lambda *args, **kwargs: None
import seaborn as sns
import base64

# 靜音 Streamlit 的內部警告與日誌錯誤
import logging
logging.getLogger("streamlit").setLevel(logging.ERROR)
os.environ["STREAMLIT_LOG_LEVEL"] = "error"
os.environ["STREAMLIT_SERVER_STATE_STORAGE"] = "memory"

import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="streamlit")
# 防止 Streamlit 的警告輸出到 stderr
logging.getLogger("streamlit.runtime.scriptrunner_utils.script_run_context").disabled = True
logging.getLogger("streamlit.runtime.caching.cache_data_api").disabled = True

# 將專案根目錄固定移到最前，避免直接執行時同名 LLM_as_a_Judge.py
# 遮蔽 LLM_as_a_Judge 套件。
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir in sys.path:
    sys.path.remove(parent_dir)
sys.path.insert(0, parent_dir)

# 導入 BadmintonAI 核心模組
from config.prompts import (
    create_minimal_system_prompt,
    create_metadata_system_prompt,
    create_system_prompt,
    create_enhancement_system_prompt,
    create_test_enhancement_system_prompt,
    create_court_metadata_priority_instruction,
    create_insight_prompt
)
from utils.data_loader import load_all_data, filter_schema_and_definitions
from utils.ai_client import initialize_client
from utils.analysis_workflow import (
    extract_token_usage,
    run_prompt_enhancement,
    run_code_generation,
    run_code_execution_loop,
    run_insight_generation
)
from utils.paths import COURT_PLACE_FILE
from utils.model_compat import temperature_kwargs
from LLM_as_a_Judge.judge_prompt import create_judge_prompt
from LLM_as_a_Judge.evaluation_records import EvaluationLedger
from LLM_as_a_Judge.mode_config import (
    TEST_MODE,
    enables_output_template_lab,
    get_mode_label,
    get_mode_profile,
    resolve_enable_step1,
    validate_evaluator_mode,
)
from LLM_as_a_Judge.output_contract import validate_output_contract
from LLM_as_a_Judge.validation_sets import (
    TEMPLATE_COMPOSITE_1,
    TEMPLATE_EXPANSION_5,
    TEMPLATE_GENERALIZATION_5,
    TEMPLATE_MINIMAL_5,
    TEMPLATE_STRATIFIED_10,
)

# 環境變數在模式驗證通過後才載入。
env_path = os.path.join(parent_dir, '.env')


class PipelineExecutionError(RuntimeError):
    """程式經既有 repair 次數後仍無法執行。"""


class LLMAsAJudge:
    def __init__(self, target_questions=[1], 
                 gen_api_mode='OpenAI 官方', gen_model='gpt-5.1',
                 judge_api_mode='OpenAI 官方', judge_model='gpt-5.1',
                 mode="our_method",
                 enable_step1=None,
                 input_token_price=1,
                 output_token_price=1,
                 judge_input_token_price=None,
                 judge_output_token_price=None,
                 question_file="評估問題.txt",
                 example_file="example.ipynb",
                 skip_insight=False):
        validate_evaluator_mode(mode)
        self.target_questions = target_questions
        self.gen_api_mode = gen_api_mode
        self.gen_model = gen_model
        self.judge_api_mode = judge_api_mode
        self.judge_model = judge_model
        self.mode = mode
        self.enable_step1 = resolve_enable_step1(mode, enable_step1)
        self.enable_output_template_lab = enables_output_template_lab(mode)
        self.skip_insight = bool(skip_insight)
        self.input_token_price = input_token_price
        self.output_token_price = output_token_price
        self.judge_input_token_price = judge_input_token_price
        self.judge_output_token_price = judge_output_token_price
        self.question_file = question_file
        self.example_file = example_file
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 設置輸出路徑 (與腳本放在同一資料夾)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.base_output_dir = os.path.join(script_dir, "eval_results")
        self.run_dir = os.path.join(self.base_output_dir, f"{self.mode}_run_{self.timestamp}")
        self.plots_dir = os.path.join(self.run_dir, "plots")
        os.makedirs(self.plots_dir, exist_ok=True)
        
        self.csv_file = os.path.join(self.run_dir, "eval_results.csv")
        self.stage_usage_file = os.path.join(
            self.run_dir,
            "stage_usage.csv",
        )
        self.ipynb_file = os.path.join(self.run_dir, "eval_notebook.ipynb")
        self.summary_file = os.path.join(self.run_dir, "summary.txt")
        self.manifest_file = os.path.join(self.run_dir, "run_manifest.json")

        # API client 延遲到實際階段才初始化，避免未使用的 Key／client 副作用。
        self.gen_client = None
        self.judge_client = None
        self._env_loaded = False

        # 載入數據
        self.df, self.data_schema_info, self.column_definitions_info = load_all_data()

        # 載入場地資訊
        try:
            with open(COURT_PLACE_FILE, "r", encoding="utf-8") as f:
                self.court_place_info = f.read()
        except:
            self.court_place_info = ""

        # 準備存儲結果
        self.results = []
        self.notebook = self._create_notebook_structure()
        
        # 載入標準答案
        self.reference_answers = self._load_reference_answers_with_duplicates()
        
        # Token 累計計數器
        self.total_pipeline_input_tokens = 0
        self.total_pipeline_output_tokens = 0
        self.total_judge_tokens = 0
        self.flagged_questions = [] # 儲存低分標註的題號
        self.step1_route_records = []
        self.template_records = []
        self.insight_records = []
        self.ledger = EvaluationLedger()

    def _get_mode_label(self):
        return get_mode_label(self.mode)

    def _ensure_env_loaded(self):
        if not getattr(self, "_env_loaded", False):
            load_dotenv(dotenv_path=env_path)
            self._env_loaded = True

    def _get_api_key(self, api_mode):
        self._ensure_env_loaded()
        key_map = {
            "Claude": "ANTHROPIC_API_KEY",
            "Gemini": "GEMINI_API_KEY",
        }
        return os.getenv(key_map.get(api_mode, "OPENAI_API_KEY"))

    def _get_gen_client(self):
        """只在生成流程實際需要時建立 client。"""
        if getattr(self, "gen_client", None) is None:
            self.gen_client = initialize_client(
                self.gen_api_mode,
                self._get_api_key(self.gen_api_mode),
            )
        return self.gen_client

    def _get_judge_client(self):
        """只在 Judge 實際需要時建立 client。"""
        if getattr(self, "judge_client", None) is None:
            self.judge_client = initialize_client(
                self.judge_api_mode,
                self._get_api_key(self.judge_api_mode),
            )
        return self.judge_client

    def _record_stage_usage(
        self,
        stage,
        usage=None,
        *,
        status="completed",
        calls=1,
        attempt=None,
        model=None,
    ):
        """將階段 token 立即寫入 ledger，避免後續例外造成遺失。"""
        return self.ledger.record_stage(
            self._current_q_num,
            stage,
            usage,
            status=status,
            calls=calls,
            attempt=attempt,
            model=model or self.gen_model,
        )

    def _question_pipeline_usage(self, question_id=None):
        """取得不含 Judge 的逐題 pipeline token。"""
        return self.ledger.usage_for_question(
            question_id or self._current_q_num,
            exclude_stages={"judge"},
        )

    def _refresh_token_totals_from_ledger(self):
        """同步舊報表欄位；唯一來源為 ledger。"""
        if not hasattr(self, "ledger"):
            return
        pipeline_records = [
            item for item in self.ledger.stage_usages
            if item.stage != "judge"
        ]
        judge_records = [
            item for item in self.ledger.stage_usages
            if item.stage == "judge"
        ]
        self.total_pipeline_input_tokens = sum(
            item.input_tokens for item in pipeline_records
        )
        self.total_pipeline_output_tokens = sum(
            item.output_tokens for item in pipeline_records
        )
        self.total_judge_tokens = sum(
            item.total_tokens for item in judge_records
        )

    def _build_cost_summary(self):
        """依 generation／Judge 各自價格計算，不推測缺少的單價。"""
        self._refresh_token_totals_from_ledger()
        generation_cost = (
            self.total_pipeline_input_tokens * self.input_token_price
            + self.total_pipeline_output_tokens * self.output_token_price
        )
        judge_usage = (
            self.ledger.usage_for_stage("judge")
            if hasattr(self, "ledger")
            else {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": self.total_judge_tokens,
                "calls": 0,
            }
        )
        judge_input_price = getattr(
            self,
            "judge_input_token_price",
            None,
        )
        judge_output_price = getattr(
            self,
            "judge_output_token_price",
            None,
        )
        judge_prices_configured = (
            judge_input_price is not None
            and judge_output_price is not None
        )
        if judge_prices_configured:
            judge_cost = (
                judge_usage["input_tokens"]
                * judge_input_price
                + judge_usage["output_tokens"]
                * judge_output_price
            )
        elif judge_usage["total_tokens"] == 0:
            judge_cost = 0
        else:
            judge_cost = None
        return {
            "generation_cost": generation_cost,
            "judge_cost": judge_cost,
            "total_cost": (
                generation_cost + judge_cost
                if judge_cost is not None
                else None
            ),
            "judge_prices_configured": judge_prices_configured,
        }

    def _court_metadata_passed(self, needs_court_info):
        """回報 Step 2 實際收到的場地 metadata 類別。"""
        if not self.court_place_info:
            return "none"
        if self.mode in {"baseline_metadata", "baseline_fullprompt"}:
            return "full_court_place"
        if self.mode in {"our_method", TEST_MODE} and needs_court_info:
            return "full_court_place"
        return "none"

    def _record_step1_route(
        self,
        enhancement_result,
        required_column_groups,
        needs_court_info,
    ):
        """保存每題 Step 1 routing；只記錄，不觸發額外模型呼叫。"""
        enhancement_result = enhancement_result or {}
        normalized = enhancement_result.get("normalized_result", {})
        trace = {
            "question_id": getattr(self, "_current_q_num", None),
            "step1_enabled": bool(self.enable_step1),
            "raw_response": enhancement_result.get("raw_response", ""),
            "normalized_result": normalized,
            "needs_court_info": bool(needs_court_info),
            "needs_court_info_llm": enhancement_result.get(
                "needs_court_info_llm"
            ),
            "needs_court_info_source": enhancement_result.get(
                "needs_court_info_source",
                "step1_disabled" if not self.enable_step1 else "unavailable",
            ),
            "semantic_court_signal": bool(
                enhancement_result.get("semantic_court_signal", False)
            ),
            "parse_error": enhancement_result.get("parse_error", ""),
            "required_column_groups": list(required_column_groups or []),
            "output_contract": normalized.get("output_contract"),
            "output_contract_status": enhancement_result.get(
                "output_contract_status",
                "not_requested",
            ),
            "output_contract_route": enhancement_result.get(
                "output_contract_route",
                "existing_free_code",
            ),
            "output_contract_errors": list(
                enhancement_result.get("output_contract_errors", [])
            ),
            "output_template_lab_enabled": bool(
                self.enable_output_template_lab
            ),
            "court_metadata_passed": self._court_metadata_passed(
                needs_court_info
            ),
        }
        records = getattr(self, "step1_route_records", [])
        records = [
            item for item in records
            if item.get("question_id") != trace["question_id"]
        ]
        records.append(trace)
        self.step1_route_records = records
        self._current_step1_trace = trace

    def _step1_trace_markdown(self):
        """產生供人工快覽的 Step 1 摘要；完整 trace 留在 manifest。"""
        trace = getattr(self, "_current_step1_trace", None)
        if not trace or not trace.get("step1_enabled"):
            return ""
        metadata = (
            "完整場地資訊"
            if trace.get("court_metadata_passed") == "full_court_place"
            else "未傳入"
        )
        source = trace.get("needs_court_info_source", "unavailable")
        text = f"- 場地資訊：{metadata}（判定來源：{source}）"
        if trace.get("parse_error"):
            text += " ⚠️ Step 1 解析異常，詳見 run_manifest.json"
        return text

    def _record_template_route(self, report=None, **changes):
        """保存 test renderer 規劃、實際路徑與估計分帳。"""

        report = dict(report or {})
        report.update(changes)
        record = {
            "question_id": getattr(self, "_current_q_num", None),
            "lab_enabled": bool(self.enable_output_template_lab),
            "enabled": bool(report.get("enabled", False)),
            "contract": report.get("contract"),
            "contract_status": report.get("contract_status", "not_available"),
            "planned_route": report.get(
                "planned_route",
                "disabled" if not self.enable_output_template_lab else "pending",
            ),
            "actual_route": report.get(
                "actual_route",
                "disabled" if not self.enable_output_template_lab else "pending",
            ),
            "renderer_status": report.get(
                "renderer_status",
                "disabled" if not self.enable_output_template_lab else "not_started",
            ),
            "renderer_calls": int(report.get("renderer_calls", 0) or 0),
            "presentation_used": report.get("presentation_used", ""),
            "fallback_reason": report.get("fallback_reason", ""),
            "payload_normalized": bool(
                report.get("payload_normalized", False)
            ),
            "artifact_nonempty": report.get("artifact_nonempty"),
            "requires_insight": bool(
                report.get("requires_insight", False)
            ),
            "code_generation_output_tokens": int(
                report.get("code_generation_output_tokens", 0) or 0
            ),
            "code_generation_input_tokens": int(
                report.get("code_generation_input_tokens", 0) or 0
            ),
            "analysis_input_tokens_estimated": int(
                report.get("analysis_input_tokens_estimated", 0) or 0
            ),
            "presentation_input_tokens_estimated": int(
                report.get("presentation_input_tokens_estimated", 0) or 0
            ),
            "analysis_output_tokens_estimated": int(
                report.get("analysis_output_tokens_estimated", 0) or 0
            ),
            "presentation_output_tokens_estimated": int(
                report.get("presentation_output_tokens_estimated", 0) or 0
            ),
            "token_split_is_estimate": bool(
                report.get("token_split_is_estimate", False)
            ),
        }
        records = getattr(self, "template_records", [])
        records = [
            item for item in records
            if item.get("question_id") != record["question_id"]
        ]
        records.append(record)
        self.template_records = records
        self._current_template_record = record

    def _current_template_fields(self):
        """取得逐題 CSV 共用的 renderer 與估計 token 欄位。"""

        record = getattr(self, "_current_template_record", {})
        return {
            "template_lab_enabled": bool(self.enable_output_template_lab),
            "template_planned_route": record.get("planned_route", "disabled"),
            "template_actual_route": record.get("actual_route", "disabled"),
            "renderer_status": record.get("renderer_status", "disabled"),
            "renderer_calls": int(record.get("renderer_calls", 0) or 0),
            "renderer_fallback_reason": record.get("fallback_reason", ""),
            "renderer_payload_normalized": bool(
                record.get("payload_normalized", False)
            ),
            "renderer_artifact_nonempty": record.get("artifact_nonempty"),
            "requires_insight": bool(record.get("requires_insight", False)),
            "analysis_output_tokens_estimated": int(
                record.get("analysis_output_tokens_estimated", 0) or 0
            ),
            "presentation_output_tokens_estimated": int(
                record.get("presentation_output_tokens_estimated", 0) or 0
            ),
            "token_split_is_estimate": bool(
                record.get("token_split_is_estimate", False)
            ),
            "analysis_input_tokens_estimated": int(
                record.get("analysis_input_tokens_estimated", 0) or 0
            ),
            "presentation_input_tokens_estimated": int(
                record.get("presentation_input_tokens_estimated", 0) or 0
            ),
        }

    def _template_trace_markdown(self):
        record = getattr(self, "_current_template_record", None)
        if not record or not record.get("lab_enabled"):
            return ""
        contract = record.get("contract") or {}
        presentations = ", ".join(contract.get("presentation", [])) or "未指定"
        route = record.get("actual_route", "pending")
        status = record.get("renderer_status", "not_started")
        text = f"- 輸出：{presentations}；renderer：{route} / {status}"
        fallback_reason = record.get("fallback_reason", "")
        if fallback_reason:
            compact_reason = " ".join(str(fallback_reason).split())[:160]
            text += f"；fallback：{compact_reason}"
        return text

    def _notebook_routing_markdown(self):
        """將必要 routing 狀態合併為單一短 cell。"""

        lines = [
            item for item in (
                self._step1_trace_markdown(),
                self._template_trace_markdown(),
            )
            if item
        ]
        if not lines:
            return ""
        return "### 流程摘要\n\n" + "\n".join(lines)

    def _run_insight_step(self, enhanced_prompt, analysis_context):
        """執行或略過洞察生成，並統一回傳 token 合約。"""
        if self.skip_insight:
            return {
                "insight": "已依 SKIP_INSIGHT 設定略過洞察生成。",
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "status": "skipped",
                "skipped": True,
            }

        insight_prompt = create_insight_prompt(
            enhanced_prompt,
            analysis_context,
        )
        result = run_insight_generation(
            self._get_gen_client(),
            self.gen_model,
            "你是一位專業羽球教練與數據戰術大師。精簡提供戰術洞察。",
            insight_prompt,
        )
        input_tokens = int(result.get("input_tokens", 0) or 0)
        output_tokens = int(result.get("output_tokens", 0) or 0)
        total_tokens = int(result.get("total_tokens", 0) or 0)
        if not total_tokens:
            total_tokens = input_tokens + output_tokens
        return {
            "insight": result.get("insight", ""),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "status": "generated",
            "skipped": False,
        }

    def _record_insight_usage(self, insight_result):
        """保存逐題洞察狀態與 token，不改變 pipeline token 計算。"""
        insight_result = insight_result or {}
        input_tokens = int(insight_result.get("input_tokens", 0) or 0)
        output_tokens = int(insight_result.get("output_tokens", 0) or 0)
        total_tokens = int(insight_result.get("total_tokens", 0) or 0)
        if not total_tokens:
            total_tokens = input_tokens + output_tokens
        template_record = getattr(self, "_current_template_record", {})
        requires_insight = bool(template_record.get("requires_insight", False))
        status = insight_result.get("status", "not_reached")
        skipped = bool(insight_result.get("skipped", False))
        if status == "generated":
            completion_status = "complete"
        elif status == "failed":
            completion_status = "insight_failed"
        elif skipped and requires_insight:
            completion_status = "evidence_only_insight_skipped"
        elif skipped:
            completion_status = "analysis_complete_insight_skipped"
        else:
            completion_status = "not_reached"
        record = {
            "question_id": getattr(self, "_current_q_num", None),
            "configured_skip": bool(self.skip_insight),
            "skipped": skipped,
            "status": status,
            "requires_insight": requires_insight,
            "evaluation_gate": (
                "code_logic" if self.skip_insight else "end_to_end"
            ),
            "answer_completion_status": completion_status,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        }
        records = getattr(self, "insight_records", [])
        records = [
            item for item in records
            if item.get("question_id") != record["question_id"]
        ]
        records.append(record)
        self.insight_records = records
        self._current_insight_record = record

    def _current_insight_fields(self):
        """取得 CSV／錯誤紀錄共用的逐題洞察欄位。"""
        record = getattr(self, "_current_insight_record", {})
        return {
            "skip_insight": bool(self.skip_insight),
            "insight_status": record.get("status", "not_reached"),
            "insight_input_tokens": int(record.get("input_tokens", 0) or 0),
            "insight_output_tokens": int(record.get("output_tokens", 0) or 0),
            "insight_tokens": int(record.get("total_tokens", 0) or 0),
            "requires_insight": bool(record.get("requires_insight", False)),
            "evaluation_gate": record.get("evaluation_gate", "end_to_end"),
            "answer_completion_status": record.get(
                "answer_completion_status",
                "not_reached",
            ),
        }

    def _current_question_state_fields(self):
        """取得 CSV 共用的逐題生命週期欄位。"""
        record = self.ledger.questions.get(self._current_q_num)
        if not record:
            return {
                "status": "pending",
                "execution_success": None,
                "execution_error": "",
                "repair_attempts": 0,
                "judge_status": "not_requested",
            }
        return {
            "status": record.status,
            "execution_success": record.execution_success,
            "execution_error": record.execution_error,
            "repair_attempts": record.repair_attempts,
            "judge_status": record.judge_status,
        }

    def _insight_markdown(self, insight_text):
        """建立 notebook 使用的洞察區塊與 skip 明確標記。"""
        if self.skip_insight:
            status = getattr(
                self,
                "_current_insight_record",
                {},
            ).get("status", "not_reached")
            if status == "not_reached":
                return (
                    "### 數據洞察\n"
                    "> SKIP_INSIGHT=True；本題流程在洞察階段前中斷，"
                    "未呼叫洞察 LLM，洞察 token 為 0。"
                )
            completion_status = getattr(
                self,
                "_current_insight_record",
                {},
            ).get("answer_completion_status")
            if completion_status == "evidence_only_insight_skipped":
                return (
                    "### 數據洞察\n"
                    "> SKIP_INSIGHT=True；分析證據已完成，"
                    "但本題最終洞察／建議未產生；洞察 token 為 0。"
                )
            return (
                "### 數據洞察\n"
                "> 已依 SKIP_INSIGHT 設定略過洞察生成；"
                "本題洞察 token 為 0。"
            )
        return f"### 數據洞察\n{insight_text}"

    def _build_summary_text(self):
        self._refresh_token_totals_from_ledger()
        total_items = len(self.target_questions)
        total_pipeline_tokens = self.total_pipeline_input_tokens + self.total_pipeline_output_tokens
        total_tokens = total_pipeline_tokens + self.total_judge_tokens
        costs = self._build_cost_summary()

        lines = [
            f"目標題數: {total_items}",
            f"架構: {self._get_mode_label()}",
            f"生成模型: {self.gen_model}",
            f"裁判模型: {self.judge_model}",
            f"SKIP_INSIGHT: {self.skip_insight}",
            "",
            f"總計 Token 消耗統計:",
            f"- 總計產出 Token (input): {self.total_pipeline_input_tokens:,}",
            f"- 總計產出 Token (output): {self.total_pipeline_output_tokens:,}",
            f"- 總計評分 Token: {self.total_judge_tokens:,}",
            f"- Generation 成本: {costs['generation_cost']:,}",
            (
                f"- Judge 成本: {costs['judge_cost']:,}"
                if costs["judge_cost"] is not None
                else "- Judge 成本: 未設定 Judge input/output 單價"
            ),
            (
                f"- 總成本: {costs['total_cost']:,}"
                if costs["total_cost"] is not None
                else "- 總成本: 部分單價未設定"
            ),
            f"- 項目總計 Token: {total_tokens:,}",
        ]

        insight_records = getattr(self, "insight_records", [])
        insight_input_tokens = sum(
            item.get("input_tokens", 0) for item in insight_records
        )
        insight_output_tokens = sum(
            item.get("output_tokens", 0) for item in insight_records
        )
        lines.append(
            "- 洞察 Token (input/output): "
            f"{insight_input_tokens:,}/{insight_output_tokens:,}"
        )
        lines.append(
            "- 評估 gate: "
            f"{'code_logic' if self.skip_insight else 'end_to_end'}"
        )

        evaluated_results = [
            item for item in self.results
            if item.get("judge_status") == "judged"
            and isinstance(item.get("code_correct"), bool)
        ]
        if evaluated_results:
            correct_count = sum(
                1 for item in evaluated_results
                if item["code_correct"]
            )
            total_count = len(evaluated_results)
            correct_ratio = correct_count / total_count
            lines.extend([
                "",
                f"正確比例: {correct_count}/{total_count} ({correct_ratio:.2%})",
            ])

        question_records = (
            self.ledger.question_dicts()
            if hasattr(self, "ledger")
            else []
        )
        if question_records:
            status_counts = {}
            for record in question_records:
                status = record["status"]
                status_counts[status] = status_counts.get(status, 0) + 1
            lines.extend([
                "",
                f"實際處理題數: {len(question_records)}",
                "逐題生命週期統計:",
            ])
            for status in sorted(status_counts):
                lines.append(f"- {status}: {status_counts[status]}")

            correct_ids = [
                item["question_id"] for item in self.results
                if item.get("judge_status") == "judged"
                and item.get("code_correct") is True
            ]
            incorrect_ids = [
                item["question_id"] for item in self.results
                if item.get("judge_status") == "judged"
                and item.get("code_correct") is False
            ]
            unscored_ids = [
                item["question_id"] for item in self.results
                if item.get("judge_status") != "judged"
            ]
            execution_failed_ids = [
                record["question_id"] for record in question_records
                if record["execution_success"] is False
            ]
            lines.extend([
                "",
                "題目列表:",
                f"- 正確: {correct_ids or 'none'}",
                f"- 錯誤: {incorrect_ids or 'none'}",
                f"- 未評分: {unscored_ids or 'none'}",
                f"- 執行失敗: {execution_failed_ids or 'none'}",
            ])

        if hasattr(self, "ledger") and self.ledger.stage_usages:
            lines.extend(["", "各階段 Token:"])
            stage_names = []
            for record in self.ledger.stage_usages:
                if record.stage not in stage_names:
                    stage_names.append(record.stage)
            for stage in stage_names:
                usage = self.ledger.usage_for_stage(stage)
                lines.append(
                    f"- {stage}: input={usage['input_tokens']}, "
                    f"output={usage['output_tokens']}, "
                    f"total={usage['total_tokens']}, "
                    f"calls={usage['calls']}"
                )

        route_records = getattr(self, "step1_route_records", [])
        if route_records:
            lines.extend(["", "Step 1 metadata routing:"])
            for trace in route_records:
                groups = ", ".join(trace["required_column_groups"]) or "none"
                lines.append(
                    f"- Q{trace['question_id']}: "
                    f"enabled={trace['step1_enabled']}, "
                    f"needs_court_info={trace['needs_court_info']}, "
                    f"source={trace['needs_court_info_source']}, "
                    f"metadata={trace['court_metadata_passed']}, "
                    f"groups={groups}"
                )

        contract_records = [
            trace for trace in route_records
            if trace.get("output_template_lab_enabled")
        ]
        if contract_records:
            status_counts = {}
            route_counts = {}
            for trace in contract_records:
                status = trace.get("output_contract_status", "unavailable")
                route = trace.get("output_contract_route", "unavailable")
                status_counts[status] = status_counts.get(status, 0) + 1
                route_counts[route] = route_counts.get(route, 0) + 1
            lines.extend([
                "",
                "test mode 輸出契約:",
                f"- 驗證狀態: {status_counts}",
                f"- 建議路徑: {route_counts}",
                "- 此區只統計 Step 1 合約；實際路徑見 test mode renderer",
            ])

        template_records = getattr(self, "template_records", [])
        active_template_records = [
            item for item in template_records if item.get("lab_enabled")
        ]
        if active_template_records:
            route_counts = {}
            fallback_ids = []
            normalized_ids = []
            empty_artifact_ids = []
            for record in active_template_records:
                route = record.get("actual_route", "unavailable")
                route_counts[route] = route_counts.get(route, 0) + 1
                if record.get("fallback_reason"):
                    fallback_ids.append(record.get("question_id"))
                if record.get("payload_normalized"):
                    normalized_ids.append(record.get("question_id"))
                if record.get("renderer_status") == "empty":
                    empty_artifact_ids.append(record.get("question_id"))
            analysis_estimate = sum(
                item.get("analysis_output_tokens_estimated", 0)
                for item in active_template_records
            )
            presentation_estimate = sum(
                item.get("presentation_output_tokens_estimated", 0)
                for item in active_template_records
            )
            analysis_input_estimate = sum(
                item.get("analysis_input_tokens_estimated", 0)
                for item in active_template_records
            )
            presentation_input_estimate = sum(
                item.get("presentation_input_tokens_estimated", 0)
                for item in active_template_records
            )
            fallback_generation_input = sum(
                item.get("code_generation_input_tokens", 0)
                for item in active_template_records
                if item.get("fallback_reason")
            )
            fallback_generation_output = sum(
                item.get("code_generation_output_tokens", 0)
                for item in active_template_records
                if item.get("fallback_reason")
            )
            lines.extend([
                "",
                "test mode renderer:",
                f"- 實際路徑: {route_counts}",
                f"- Fallback 題號: {fallback_ids or 'none'}",
                f"- Payload 正規化題號: {normalized_ids or 'none'}",
                f"- 空輸出產物題號: {empty_artifact_ids or 'none'}",
                "- Code output token 分配為估計值，不是 API 分階段回報",
                f"- 分析／呈現 input token 估計: {analysis_input_estimate}/{presentation_input_estimate}",
                f"- 分析／呈現 output token 估計: {analysis_estimate}/{presentation_estimate}",
                f"- Fallback 題目的 Step 2 input/output token: {fallback_generation_input}/{fallback_generation_output}",
            ])

        if insight_records:
            lines.extend(["", "逐題洞察狀態:"])
            for record in insight_records:
                lines.append(
                    f"- Q{record['question_id']}: "
                    f"status={record['status']}, "
                    f"skipped={record['skipped']}, "
                    f"completion={record.get('answer_completion_status', 'not_reached')}, "
                    f"input={record['input_tokens']}, "
                    f"output={record['output_tokens']}"
                )

        return "\n".join(lines) + "\n"

    def _build_run_manifest(self):
        """建立不含憑證的機器可讀 run 設定與洞察分帳。"""
        insight_records = getattr(self, "insight_records", [])
        profile = get_mode_profile(self.mode)
        return {
            "mode": self.mode,
            "mode_profile": {
                "prompt_kind": profile.prompt_kind,
                "enable_step1": profile.enable_step1,
                "metadata_policy": profile.metadata_policy,
                "output_template_lab": profile.output_template_lab,
            },
            "settings": {
                "skip_insight": bool(self.skip_insight),
                "only_generation": bool(
                    getattr(self, "only_generation", False)
                ),
                "target_questions": list(self.target_questions),
                "generation_input_token_price": self.input_token_price,
                "generation_output_token_price": self.output_token_price,
                "judge_input_token_price": getattr(
                    self,
                    "judge_input_token_price",
                    None,
                ),
                "judge_output_token_price": getattr(
                    self,
                    "judge_output_token_price",
                    None,
                ),
            },
            "models": {
                "generation": self.gen_model,
                "judge": self.judge_model,
            },
            "insight": {
                "input_tokens": sum(
                    item.get("input_tokens", 0)
                    for item in insight_records
                ),
                "output_tokens": sum(
                    item.get("output_tokens", 0)
                    for item in insight_records
                ),
                "questions": insight_records,
            },
            "evaluation": {
                "gate": (
                    "code_logic" if self.skip_insight else "end_to_end"
                ),
                "skip_insight": bool(self.skip_insight),
            },
            "step1_routes": list(
                getattr(self, "step1_route_records", [])
            ),
            "template": {
                "token_split_is_estimate": True,
                "questions": list(
                    getattr(self, "template_records", [])
                ),
            },
            "questions": (
                self.ledger.question_dicts()
                if hasattr(self, "ledger")
                else []
            ),
            "stage_usage": (
                self.ledger.stage_dicts()
                if hasattr(self, "ledger")
                else []
            ),
            "cost": (
                self._build_cost_summary()
                if hasattr(self, "ledger")
                else {}
            ),
        }

    def _load_reference_answers(self):
        """從 example.ipynb 載入各題標準答案，回傳 dict {q_num: code_str}"""
        example_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), self.example_file)
        if not os.path.exists(example_path):
            print(f"⚠️ 找不到 {self.example_file}，無法進行標準答案比對。")
            return {}
        
        try:
            with open(example_path, "r", encoding="utf-8") as f:
                nb = json.load(f)
            
            ref_dict = {}
            current_q_num = None
            
            for cell in nb["cells"]:
                content = "".join(cell["source"]).strip()
                if cell["cell_type"] == "markdown":
                    # 尋找題號，例如 "1. 周天成..."
                    match = re.match(r'^\s*(\d+)\.\s*', content)
                    if match:
                        current_q_num = int(match.group(1))
                elif cell["cell_type"] == "code" and current_q_num is not None:
                    # 當遇到題號後的下一個 code cell，視為標準答案
                    if current_q_num not in ref_dict:
                        ref_dict[current_q_num] = content
                        current_q_num = None # 清空以等待下一題
            
            return ref_dict
            
        except Exception as e:
            print(f"⚠️ 載入標準答案失敗: {e}")
            return {}

    def _load_reference_answers_with_duplicates(self):
        """從 example.ipynb 載入各題標準答案，支援同題號多個 code cell。"""
        example_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), self.example_file)

        try:
            with open(example_path, "r", encoding="utf-8") as f:
                nb = json.load(f)

            ref_dict = {}
            current_q_num = None

            for cell in nb["cells"]:
                content = "".join(cell.get("source", [])).strip()
                if cell.get("cell_type") == "markdown":
                    match = re.match(r'^\s*(\d+)\.\s*', content)
                    if match:
                        current_q_num = int(match.group(1))
                elif cell.get("cell_type") == "code" and current_q_num is not None:
                    if content:
                        ref_dict.setdefault(current_q_num, []).append(content)
                    current_q_num = None

            return ref_dict

        except Exception as e:
            print(f"⚠️ 載入標準答案失敗: {e}")
            return {}

    def _build_system_prompt(self, required_column_groups, needs_court_info):
        """依模式建立對應層級的 system prompt。"""
        profile = get_mode_profile(self.mode)
        if profile.prompt_kind == "minimal":
            return create_minimal_system_prompt(self.data_schema_info)

        if profile.prompt_kind == "metadata":
            return create_metadata_system_prompt(
                self.data_schema_info,
                self.column_definitions_info,
                self.court_place_info
            )

        if profile.prompt_kind == "full":
            return create_system_prompt(
                self.data_schema_info,
                self.column_definitions_info,
                self.court_place_info
            )

        if profile.prompt_kind == "filtered_full":
            filtered_schema, filtered_defs = filter_schema_and_definitions(
                required_column_groups,
                self.data_schema_info,
                self.column_definitions_info
            )
            prompt = create_system_prompt(
                filtered_schema,
                filtered_defs,
                self.court_place_info if needs_court_info else None
            )
            if needs_court_info and self.court_place_info:
                prompt += create_court_metadata_priority_instruction()
            return prompt

        raise ValueError(f"不支援的模式: {self.mode}")

    def _create_notebook_structure(self):
        """建立 Jupyter Notebook 基本結構"""
        return {
            "cells": [],
            "metadata": {
                "kernelspec": {
                    "display_name": "Python 3",
                    "language": "python",
                    "name": "python3"
                },
                "language_info": {
                    "codemirror_mode": {"name": "ipython", "version": 3},
                    "file_extension": ".py",
                    "mimetype": "text/x-python",
                    "name": "python",
                    "nbconvert_exporter": "python",
                    "pygments_lexer": "ipython3",
                    "version": "3.8.0"
                }
            },
            "nbformat": 4,
            "nbformat_minor": 4
        }
        
    def _add_notebook_markdown(self, text):
        cell = {
            "cell_type": "markdown",
            "metadata": {},
            "source": [line + "\n" for line in text.split("\n")]
        }
        self.notebook["cells"].append(cell)

    @staticmethod
    def _compact_notebook_stdout(stdout, max_lines=20, max_chars=3000):
        """限制 notebook stdout 大小，只保留人工審查所需結果。"""

        text = str(stdout or "").strip()
        if not text:
            return ""
        lines = text.splitlines()
        truncated = len(lines) > max_lines
        text = "\n".join(lines[:max_lines])
        if len(text) > max_chars:
            text = text[:max_chars].rstrip()
            truncated = True
        if truncated:
            text += "\n…（輸出已截斷；notebook 僅保留重點）"
        return text + "\n"

    def _add_notebook_code(self, code, b64_images=None, stdout=""):
        source = [line + "\n" for line in code.split("\n")]
        cell = {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": source
        }

        compact_stdout = self._compact_notebook_stdout(stdout)
        if compact_stdout:
            cell["outputs"].append({
                "name": "stdout",
                "output_type": "stream",
                "text": [compact_stdout],
            })
        
        # 插入圖片輸出
        for b64 in b64_images or []:
            cell["outputs"].append({
                "data": {
                    "image/png": b64
                },
                "metadata": {},
                "output_type": "display_data"
            })
            
        self.notebook["cells"].append(cell)

    def _checkpoint_export(self):
        """每題後先保存一次，避免流程中途中斷時前功盡棄。"""
        try:
            self._export_files(show_message=False)
        except Exception as e:
            print(f"⚠️ 保存 checkpoint 失敗：{e}")

    def _atomic_write_text(self, path, content, encoding="utf-8"):
        """同目錄暫存後原子替換，失敗時保留上一份有效檔案。"""
        temp_path = f"{path}.tmp"
        try:
            with open(temp_path, "w", encoding=encoding) as file:
                file.write(content)
            os.replace(temp_path, path)
        except Exception:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise

    def _atomic_write_csv(self, dataframe, path):
        """原子寫入 CSV。"""
        temp_path = f"{path}.tmp"
        try:
            dataframe.to_csv(
                temp_path,
                index=False,
                encoding="utf-8-sig",
            )
            os.replace(temp_path, path)
        except Exception:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise

    def _record_question_failure(self, q_text, error, pipeline_input_tokens=0, pipeline_output_tokens=0,
                                 required_column_groups=None,
                                 code_to_execute="", insight_text="", b64_images=None, only_generation=False):
        """記錄單題流程中斷，並保留當下已完成內容。"""
        required_column_groups = required_column_groups or []
        b64_images = b64_images or []
        error_text = f"流程中斷：{type(error).__name__}: {error}"
        code_to_execute = (
            code_to_execute
            or getattr(self, "_current_code_to_execute", "")
        )
        if self._current_q_num in self.ledger.questions:
            question_record = self.ledger.questions[self._current_q_num]
            if question_record.status != "execution_failed":
                self.ledger.update_question(
                    self._current_q_num,
                    status="pipeline_failed",
                    needs_review=True,
                    judge_status="not_run_pipeline_failed",
                )
            usage = self._question_pipeline_usage()
            pipeline_input_tokens = usage["input_tokens"]
            pipeline_output_tokens = usage["output_tokens"]
        pipeline_total_tokens = pipeline_input_tokens + pipeline_output_tokens

        self._refresh_token_totals_from_ledger()

        res_item = {
            "question_id": self._current_q_num,
            "question_text": q_text,
            "pipeline_input_tokens": pipeline_input_tokens,
            "pipeline_output_tokens": pipeline_output_tokens,
            "pipeline_tokens": pipeline_total_tokens,
            "judge_input_tokens": 0,
            "judge_output_tokens": 0,
            "judge_tokens": 0,
            "total_tokens": pipeline_total_tokens,
            "required_groups": ", ".join(required_column_groups),
            "pipeline_type": self.mode,
            "code_correct": False,
            "code_reasoning": error_text,
            "needs_review": True
        }
        res_item.update(self._current_insight_fields())
        res_item.update(self._current_template_fields())
        res_item.update(self._current_question_state_fields())
        self.results.append(res_item)
        if self._current_q_num not in self.flagged_questions:
            self.flagged_questions.append(self._current_q_num)

        q_header = f"## 題號 {self._current_q_num}"
        if not only_generation:
            q_header += " (*)"

        group_text = ", ".join(required_column_groups) if required_column_groups else "未判定（流程中斷）"
        self._add_notebook_markdown(
            f"{q_header}\n**問題**: {q_text}\n> **使用的資料欄位群組**: `{group_text}`"
        )
        routing_markdown = self._notebook_routing_markdown()
        if routing_markdown:
            self._add_notebook_markdown(routing_markdown)
        if code_to_execute:
            self._add_notebook_code(
                code_to_execute,
                b64_images,
                getattr(self, "_current_execution_output", ""),
            )

        failure_md = f"### 執行中斷\n\n> **錯誤**: {error_text}"
        if insight_text or self.skip_insight:
            self._add_notebook_markdown(
                f"{self._insight_markdown(insight_text)}"
                f"\n\n---\n{failure_md}"
            )
        else:
            self._add_notebook_markdown(failure_md)

    def _load_target_questions(self, filepath=None):
        """讀取問題集並篩選出 target_questions 中的問題 (保證與腳本在同一資料夾)"""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        filepath = filepath or self.question_file
        fullpath = os.path.join(script_dir, filepath)
            
        questions = []
        try:
            with open(fullpath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                for line in lines:
                    line = line.strip()
                    if not line: continue
                    try:
                        # 格式通常為 "1: 周天成使用..."
                        num_str, q_text = line.split(":", 1)
                        q_num = int(num_str.strip())
                        if q_num in self.target_questions:
                            questions.append({"編號": q_num, "問題": q_text.strip()})
                    except:
                        pass
        except Exception as e:
            print(f"❌ 讀取問題檔案失敗: {e}")
            
        return questions

    def _run_pipeline(self, prompt):
        """執行 BadmintonAI 的核心邏輯 (與 front_page.py / analysis_workflow 同步)"""
        if self._current_q_num not in self.ledger.questions:
            self.ledger.start_question(self._current_q_num, prompt)
        template_context = None
        self._record_template_route()

        # --- Step 1: 轉化與優化使用者問題 ---
        print("▶ Step 1: 分析與優化問題...")
        pipeline_input_tokens = 0
        pipeline_output_tokens = 0
        required_column_groups = []
        needs_court_info = False
        enhance_res = None
        self._record_insight_usage(
            {
                "status": "not_reached",
                "skipped": False,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            }
        )
        self._record_step1_route(
            enhance_res,
            required_column_groups,
            needs_court_info,
        )
        if self.enable_step1:
            if self.enable_output_template_lab:
                enhancement_system_prompt = create_test_enhancement_system_prompt()
                output_contract_validator = validate_output_contract
            else:
                enhancement_system_prompt = create_enhancement_system_prompt()
                output_contract_validator = None
            try:
                enhance_res = run_prompt_enhancement(
                    self._get_gen_client(),
                    self.gen_model,
                    enhancement_system_prompt,
                    prompt,
                    [],
                    output_contract_validator=output_contract_validator,
                )
            except Exception:
                self._record_stage_usage(
                    "step1",
                    status="failed",
                    calls=1,
                )
                raise
            enhanced_prompt = enhance_res["enhanced_prompt"]
            needs_court_info = enhance_res["needs_court_info"]
            required_column_groups = enhance_res.get("required_column_groups", [])
            pipeline_input_tokens += enhance_res.get("input_tokens", 0)
            pipeline_output_tokens += enhance_res.get("output_tokens", 0)
            self._record_stage_usage("step1", enhance_res)
        else:
            enhanced_prompt = prompt
            self._record_stage_usage(
                "step1",
                status="skipped",
                calls=0,
            )
        
        # --- Step 2: 生成分析程式碼 ---
        print("▶ Step 2: 生成程式碼...")
        system_prompt = self._build_system_prompt(required_column_groups, needs_court_info)
        base_system_prompt = system_prompt
        if self.enable_output_template_lab:
            from LLM_as_a_Judge.test_output_adapter import (
                prepare_template_execution,
            )

            template_context = prepare_template_execution(
                system_prompt,
                enhance_res,
            )
            system_prompt = template_context.system_prompt
            self._record_template_route(template_context.report)
        self._record_step1_route(
            enhance_res,
            required_column_groups,
            needs_court_info,
        )
        try:
            gen_res = run_code_generation(
                self._get_gen_client(),
                self.gen_model,
                system_prompt,
                enhanced_prompt,
                [],
            )
        except Exception:
            self._record_stage_usage(
                "code_generation",
                status="failed",
                calls=1,
            )
            raise
        code_to_execute = gen_res["code"]
        pipeline_input_tokens += gen_res.get("input_tokens", 0)
        pipeline_output_tokens += gen_res.get("output_tokens", 0)
        self._record_stage_usage("code_generation", gen_res)
        if template_context is not None:
            from LLM_as_a_Judge.test_output_adapter import (
                estimate_code_token_split,
                estimate_prompt_token_split,
            )

            token_split = estimate_code_token_split(
                code_to_execute,
                gen_res.get("output_tokens", 0),
            )
            prompt_token_split = estimate_prompt_token_split(
                base_system_prompt,
                system_prompt,
                enhanced_prompt,
                gen_res.get("input_tokens", 0),
            )
            template_context.report.update({
                "code_generation_input_tokens": int(
                    gen_res.get("input_tokens", 0) or 0
                ),
                "code_generation_output_tokens": int(
                    gen_res.get("output_tokens", 0) or 0
                ),
                **token_split,
                **prompt_token_split,
                "token_split_is_estimate": True,
            })
            self._record_template_route(template_context.report)
        
        # --- Step 3: 執行程式碼並在失敗時自動透過 AI 修復 ---
        print("▶ Step 3: 執行程式...")
        
        try:
            execution_kwargs = {"max_retries": 3}
            if (
                template_context is not None
                and template_context.extended_globals
            ):
                execution_kwargs["extended_globals"] = (
                    template_context.extended_globals
                )
            exec_loop_res = run_code_execution_loop(
                self._get_gen_client(),
                self.gen_model,
                code_to_execute,
                self.df,
                system_prompt,
                enhanced_prompt,
                **execution_kwargs,
            )
        except Exception:
            self._record_stage_usage(
                "execution",
                status="failed",
                calls=0,
            )
            raise
        pipeline_input_tokens += exec_loop_res.get("input_tokens", 0)
        pipeline_output_tokens += exec_loop_res.get("output_tokens", 0)
        for attempt_usage in exec_loop_res.get("attempt_usages", []):
            self._record_stage_usage(
                "repair",
                attempt_usage,
                attempt=attempt_usage.get("attempt"),
            )
        
        code_to_execute = exec_loop_res["final_code"]
        exec_result = exec_loop_res["exec_result"]
        if template_context is not None:
            from LLM_as_a_Judge.test_output_adapter import (
                finalize_template_report,
            )

            finalize_template_report(template_context.report)
            self._record_template_route(template_context.report)
            renderer_status = template_context.report.get(
                "renderer_status",
                "skipped",
            )
            self._record_stage_usage(
                "renderer",
                status=renderer_status,
                calls=int(
                    template_context.report.get("renderer_calls", 0) or 0
                ),
            )
        self._current_code_to_execute = code_to_execute
        execution_success = bool(exec_loop_res.get("success", False))
        execution_error = (
            exec_result.get("error", "")
            if exec_result
            else "未取得程式執行結果"
        )
        self._record_stage_usage(
            "execution",
            status="completed" if execution_success else "failed",
            calls=0,
        )
        self.ledger.update_question(
            self._current_q_num,
            status=(
                "execution_succeeded"
                if execution_success
                else "execution_failed"
            ),
            execution_success=execution_success,
            execution_error=execution_error,
            repair_attempts=exec_loop_res.get("repair_attempts", 0),
            judge_status=(
                "not_requested"
                if execution_success
                else "not_run_execution_failed"
            ),
            needs_review=not execution_success,
        )
        if not execution_success:
            raise PipelineExecutionError(
                execution_error or "程式經 repair 後仍無法執行"
            )
        
        # 抓取最終產生的圖片
        final_figs = []
        summary_info = {}
        execution_output = ""
        
        if exec_result:
            final_figs = exec_result.get("figs", [])
            summary_info = exec_result.get("summary_info", {})
            execution_output = exec_result.get("stdout", "")
        self._current_execution_output = execution_output
            
        b64_images = []
        plot_paths = []
        for i, fig in enumerate(final_figs):
            if fig is None or not hasattr(fig, "savefig"):
                continue
            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=300, bbox_inches="tight")
            buf.seek(0)
            
            # 存成實體檔案
            plot_filename = f"q{self._current_q_num}_plot_{i}.png"
            plot_path = os.path.join(self.plots_dir, plot_filename)
            with open(plot_path, "wb") as f_img:
                f_img.write(buf.getvalue())
            plot_paths.append(plot_path)
            
            # 轉 Base64 (For IPYNB)
            b64_images.append(base64.b64encode(buf.getvalue()).decode('utf-8'))
            
        plt.close('all') # 清除記憶體
        
        # --- Step 4: 生成數據洞察 ---
        if self.skip_insight:
            print("▶ Step 4: 已依 SKIP_INSIGHT 略過數據洞察。")
        else:
            print("▶ Step 4: 生成數據洞察...")
        if not summary_info:
            summary_info = {"提示": "AI 未輸出可供分析的變數。"}
            
        analysis_context_str = ""
        if execution_output:
            analysis_context_str += f"--- 程式執行輸出 (Stdout) ---\n{execution_output}\n\n"
        analysis_context_str += "程式碼執行後，擷取出以下核心變數與其值：\n"
        for name, val in summary_info.items():
            analysis_context_str += f"- 變數 `{name}`: {str(val)}\n"
             
        try:
            insight_res = self._run_insight_step(
                enhanced_prompt,
                analysis_context_str,
            )
        except Exception:
            self._record_insight_usage(
                {
                    "status": "failed",
                    "skipped": False,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                }
            )
            self._record_stage_usage(
                "insight",
                status="failed",
                calls=1,
            )
            raise
        self._record_insight_usage(insight_res)
        self._record_stage_usage(
            "insight",
            insight_res,
            status=insight_res.get("status", "generated"),
            calls=0 if insight_res.get("skipped") else 1,
        )
        insight_text = insight_res["insight"]
        pipeline_input_tokens += insight_res.get("input_tokens", 0)
        pipeline_output_tokens += insight_res.get("output_tokens", 0)
        
        return (
            code_to_execute,
            insight_text,
            b64_images,
            plot_paths,
            pipeline_input_tokens,
            pipeline_output_tokens,
            required_column_groups,
        )

    def _judge_result(self, question, code, ref_codes):
        """呼叫 LLM 進行評分判斷"""
        print("▶ Step 6: AI 裁判正在評核...")
        
        if not code:
            return {
                "code_correct": False,
                "reasoning": "未生成有效程式碼。",
                "judge_tokens": 0,
                "judge_input_tokens": 0,
                "judge_output_tokens": 0,
                "judge_status": "not_run_no_code",
            }

        judge_prompt = create_judge_prompt(question, code, self.column_definitions_info, ref_codes)
        
        messages = [{"role": "user", "content": judge_prompt}]
        judge_tokens = 0
        judge_input_tokens = 0
        judge_output_tokens = 0
        
        try:
            response = self._get_judge_client().chat.completions.create(
                model=self.judge_model,
                messages=messages,
                **temperature_kwargs(self.judge_model, 0.0),
            )
            raw_eval = response.choices[0].message.content.strip()
            judge_usage = extract_token_usage(response)
            judge_input_tokens += judge_usage["input_tokens"]
            judge_output_tokens += judge_usage["output_tokens"]
            judge_tokens += judge_usage["total_tokens"]
            
            # 安全清理與 Parse JSON
            if "```json" in raw_eval:
                start = raw_eval.find("```json") + 7
                end = raw_eval.rfind("```")
                raw_eval = raw_eval[start:end].strip()
            elif "```" in raw_eval:
                start = raw_eval.find("```") + 3
                end = raw_eval.rfind("```")
                raw_eval = raw_eval[start:end].strip()
                
            eval_dict = json.loads(raw_eval)
            eval_dict["judge_tokens"] = judge_tokens
            eval_dict["judge_input_tokens"] = judge_input_tokens
            eval_dict["judge_output_tokens"] = judge_output_tokens
            eval_dict["judge_status"] = "judged"
            return eval_dict
            
        except Exception as e:
            print(f"❌ 裁判評分失敗: {e}")
            return {
                "code_correct": False,
                "reasoning": f"評分解析錯誤: {e}",
                "judge_tokens": judge_tokens,
                "judge_input_tokens": judge_input_tokens,
                "judge_output_tokens": judge_output_tokens,
                "judge_status": "parse_failed",
            }

    def run(self, only_generation=False):
        """執行完整的批量評估流程"""
        self.only_generation = only_generation
        questions = self._load_target_questions()
        total_items = len(questions)

        if total_items == 0:
            print("❌ 找不到目標問題，請檢查 target_questions 設定。")
            return

        print(f"\n🚀 啟動 LLM-as-a-Judge: 生成 + 評核...")
        print(f"📌 目標題數: {total_items} 題")
        print(f"🏗️ 使用架構: {self._get_mode_label()}")
        print(f"📊 生成模型: {self.gen_model} | 裁判模型: {self.judge_model}\n{'-'*50}")

        for idx, q_dict in enumerate(questions, 1):
            self._current_q_num = q_dict["編號"]
            q_text = q_dict["問題"]
            self.ledger.start_question(self._current_q_num, q_text)
            self._current_code_to_execute = ""
            self._current_execution_output = ""

            print(f"\n[{idx}/{total_items}] 處理問題 {self._current_q_num}: {q_text[:30]}...")

            code_to_execute = ""
            insight_text = ""
            b64_images = []
            pipeline_input_tokens = 0
            pipeline_output_tokens = 0
            required_column_groups = []
            try:
                # 執行分析流程
                (
                    code_to_execute,
                    insight_text,
                    b64_images,
                    plot_paths,
                    pipeline_input_tokens,
                    pipeline_output_tokens,
                    required_column_groups,
                ) = self._run_pipeline(q_text)
                pipeline_tokens = pipeline_input_tokens + pipeline_output_tokens

                judge_tokens = 0
                judge_input_tokens = 0
                judge_output_tokens = 0
                code_correct = None
                reasoning = ""
                if only_generation:
                    judge_status = "skipped_only_generation"
                    self._record_stage_usage(
                        "judge",
                        status=judge_status,
                        calls=0,
                        model=self.judge_model,
                    )
                    self.ledger.update_question(
                        self._current_q_num,
                        status="completed",
                        judge_status=judge_status,
                    )
                else:
                    ref_code = self.reference_answers.get(
                        self._current_q_num,
                        "無標準答案",
                    )
                    if ref_code == "無標準答案":
                        judge_status = "reference_missing"
                        print(
                            f"⚠️ 題號 {self._current_q_num} 在 "
                            f"{self.example_file} 找不到標準答案，"
                            "保留生成結果但不執行評分。"
                        )
                        self._record_stage_usage(
                            "judge",
                            status=judge_status,
                            calls=0,
                            model=self.judge_model,
                        )
                        self.ledger.update_question(
                            self._current_q_num,
                            status="completed",
                            judge_status=judge_status,
                            needs_review=True,
                        )
                    else:
                        eval_res = self._judge_result(
                            q_text,
                            code_to_execute,
                            ref_code,
                        )
                        judge_tokens = eval_res.get("judge_tokens", 0)
                        judge_input_tokens = eval_res.get(
                            "judge_input_tokens",
                            0,
                        )
                        judge_output_tokens = eval_res.get(
                            "judge_output_tokens",
                            0,
                        )
                        judge_status = eval_res.get(
                            "judge_status",
                            "judged",
                        )
                        self._record_stage_usage(
                            "judge",
                            {
                                "input_tokens": judge_input_tokens,
                                "output_tokens": judge_output_tokens,
                                "total_tokens": judge_tokens,
                            },
                            status=judge_status,
                            model=self.judge_model,
                        )
                        code_correct = eval_res.get("code_correct", False)
                        reasoning = eval_res.get("reasoning", "")
                        is_flagged = not code_correct
                        self.ledger.update_question(
                            self._current_q_num,
                            status="completed",
                            judge_status=judge_status,
                            code_correct=code_correct,
                            needs_review=is_flagged,
                        )
                        if (
                            is_flagged
                            and self._current_q_num
                            not in self.flagged_questions
                        ):
                            self.flagged_questions.append(
                                self._current_q_num
                            )

                self._refresh_token_totals_from_ledger()
                state_fields = self._current_question_state_fields()
                is_flagged = bool(
                    self.ledger.questions[
                        self._current_q_num
                    ].needs_review
                )
                res_item = {
                    "question_id": self._current_q_num,
                    "question_text": q_text,
                    "pipeline_input_tokens": pipeline_input_tokens,
                    "pipeline_output_tokens": pipeline_output_tokens,
                    "pipeline_tokens": pipeline_tokens,
                    "judge_input_tokens": judge_input_tokens,
                    "judge_output_tokens": judge_output_tokens,
                    "judge_tokens": judge_tokens,
                    "total_tokens": pipeline_tokens + judge_tokens,
                    "required_groups": ", ".join(required_column_groups),
                    "pipeline_type": self.mode,
                    "code_correct": code_correct,
                    "code_reasoning": reasoning,
                    "needs_review": is_flagged,
                }
                res_item.update(self._current_insight_fields())
                res_item.update(self._current_template_fields())
                res_item.update(state_fields)
                self.results.append(res_item)

                if only_generation:
                    print(
                        f"💰 消耗 Token: 產出(input) "
                        f"{pipeline_input_tokens:,} | 產出(output) "
                        f"{pipeline_output_tokens:,} | "
                        f"總計 {pipeline_tokens:,}"
                    )
                elif judge_status == "reference_missing":
                    print(
                        f"🏁 評分結果: ⚠️ 缺少 reference，未評分"
                    )
                else:
                    status_emoji = (
                        "✅ 正確" if code_correct else "❌ 錯誤"
                    )
                    print(f"🏁 評分結果: {status_emoji}")
                    print(
                        f"💰 消耗 Token: 產出(input) "
                        f"{pipeline_input_tokens:,} | 產出(output) "
                        f"{pipeline_output_tokens:,} | "
                        f"評分 {judge_tokens:,} | "
                        f"總計 {pipeline_tokens + judge_tokens:,}"
                    )

                # 構建 IPYNB 結構
                q_header = f"## 題號 {self._current_q_num}"
                if not only_generation and self._current_q_num in self.flagged_questions:
                    q_header += " (*)"

                group_info = f"\n> **使用的資料欄位群組**: `{', '.join(required_column_groups) if required_column_groups else '全欄位 (Fallback)'}`"
                self._add_notebook_markdown(f"{q_header}\n**問題**: {q_text}{group_info}")
                routing_markdown = self._notebook_routing_markdown()
                if routing_markdown:
                    self._add_notebook_markdown(routing_markdown)
                if code_to_execute:
                    self._add_notebook_code(
                        code_to_execute,
                        b64_images,
                        getattr(self, "_current_execution_output", ""),
                    )

                if not only_generation:
                    judge_md = "### 🤖 AI 裁判評分報告\n\n"
                    if judge_status == "reference_missing":
                        judge_md += (
                            "#### ⚠️ 未評分：缺少 reference\n"
                            "> 已保留程式、執行結果與 token。\n\n"
                        )
                    else:
                        status_text = (
                            "✅ 正確" if code_correct else "❌ 錯誤"
                        )
                        judge_md += (
                            f"#### 💻 程式碼評核: {status_text}\n"
                            f"> **分析意見**: {reasoning}\n\n"
                        )
                    self._add_notebook_markdown(
                        f"{self._insight_markdown(insight_text)}"
                        f"\n\n---\n{judge_md}"
                    )
                else:
                    self._add_notebook_markdown(
                        self._insight_markdown(insight_text)
                    )
            except Exception as e:
                print(f"❌ 題號 {self._current_q_num} 流程中斷：{e}")
                self._record_question_failure(
                    q_text,
                    e,
                    pipeline_input_tokens=pipeline_input_tokens,
                    pipeline_output_tokens=pipeline_output_tokens,
                    required_column_groups=required_column_groups,
                    code_to_execute=code_to_execute,
                    insight_text=insight_text,
                    b64_images=b64_images,
                    only_generation=only_generation
                )
            finally:
                self._checkpoint_export()

        # --- 列印最終 Token 統計 ---
        if total_items > 0:
            self._refresh_token_totals_from_ledger()
            total_pipeline_tokens = self.total_pipeline_input_tokens + self.total_pipeline_output_tokens
            total_tokens = total_pipeline_tokens + self.total_judge_tokens
            costs = self._build_cost_summary()
            print(f"\n{'='*50}")
            print(f"💰 總計 Token 消耗統計 ({total_items} 題):")
            print(f"  - 總計產出 Token (input): {self.total_pipeline_input_tokens:,}")
            print(f"  - 總計產出 Token (output): {self.total_pipeline_output_tokens:,}")
            print(f"  - 總計評分 Token: {self.total_judge_tokens:,}")
            print(f"  - Generation 成本: {costs['generation_cost']:,}")
            if costs["judge_cost"] is None:
                print("  - Judge 成本: 未設定 Judge input/output 單價")
                print("  - 總成本: 部分單價未設定")
            else:
                print(f"  - Judge 成本: {costs['judge_cost']:,}")
                print(f"  - 總成本: {costs['total_cost']:,}")
            print(f"  - 項目總計 Token: {total_tokens:,}")
            print(f"{'='*50}")

        evaluated_results = [
            item for item in self.results
            if item.get("judge_status") == "judged"
            and isinstance(item.get("code_correct"), bool)
        ]
        if not only_generation and evaluated_results:
            correct_count = sum(
                1 for item in evaluated_results
                if item["code_correct"]
            )
            total_count = len(evaluated_results)
            correct_ratio = correct_count / total_count
            print(f" 正確比例: {correct_count}/{total_count} ({correct_ratio:.2%})")

        self._checkpoint_export()
        
        # 顯示標註題目總結
        if not only_generation and self.flagged_questions:
            print(f"\n{'='*50}")
            print(f"發現錯誤題目 (程式碼判定不正確)")
            print(f"建議人工檢視以下題目: {', '.join(map(str, self.flagged_questions))}")
            print(f"{'='*50}")

    def _export_files(self, show_message=True):
        """匯出 CSV, IPYNB"""
        # 每種模式固定輸出逐題與階段 CSV；未執行 Judge 時欄位留空／狀態化。
        df_res = pd.DataFrame(self.results)
        self._atomic_write_csv(df_res, self.csv_file)
        stage_df = pd.DataFrame(self.ledger.stage_dicts())
        self._atomic_write_csv(stage_df, self.stage_usage_file)

        # IPYNB
        self._atomic_write_text(
            self.ipynb_file,
            json.dumps(self.notebook, ensure_ascii=False, indent=2),
        )

        # Summary
        self._atomic_write_text(
            self.summary_file,
            self._build_summary_text(),
        )

        # Run manifest
        self._atomic_write_text(
            self.manifest_file,
            json.dumps(
                self._build_run_manifest(),
                ensure_ascii=False,
                indent=2,
            ),
        )

        if show_message:
            print(f"\n📂 評估流程結束，所有輸出已儲存至目錄:\n   {self.run_dir}")

SMOKE_20 = [
    1, 10, 16, 22, 25,
    31, 37, 45, 50, 60,
    63, 67, 71, 76, 79,
    83, 85, 89, 93, 100
]

VALIDATION_40 = [
    1, 6, 10, 13, 16, 17, 18, 22, 25, 30,
    31, 34, 37, 38, 42, 45, 47, 50, 51, 60,
    61, 63, 65, 66, 67, 71, 73, 76, 79, 80,
    82, 83, 84, 85, 88, 89, 91, 93, 95, 100
]

FULL = list(range(1, 101))

if __name__ == "__main__":
    # QUESTIONS_TO_RUN = list(range(1, 101))
    # 手動測試時只保留其中一行，避免誤跑較大題組。
    # QUESTIONS_TO_RUN = list(TEMPLATE_MINIMAL_5)
    # QUESTIONS_TO_RUN = list(TEMPLATE_COMPOSITE_1)
    # QUESTIONS_TO_RUN = list(TEMPLATE_STRATIFIED_10)
    # QUESTIONS_TO_RUN = list(TEMPLATE_EXPANSION_5)
    QUESTIONS_TO_RUN = list(VALIDATION_40)

    QUESTION_FILE = "評估問題_new.txt"
    EXAMPLE_FILE = "example_new.ipynb"
    
    # --- 1. 選擇生成 (Generation) 用的 API 與模型 ---
    # GEN_API_MODE =  "Claude"
    # GEN_MODEL = "claude-sonnet-4-6"
    GEN_API_MODE =  "OpenAI 官方"
    GEN_MODEL = "gpt-5.6-luna"
    
    # --- 2. 選擇評估 (Judge) 用的 API 與模型 ---
    JUDGE_API_MODE = "OpenAI 官方"
    JUDGE_MODEL = "gpt-4o-mini"
    
    # --- 3. 流程控制 ---
    # baseline_minimal baseline_metadata baseline_fullprompt our_method test
    # test 是新輸出模板的隔離試驗模式，不會修改 our_method。
    MODE = "baseline_fullprompt"
    ONLY_GENERATION = True       # True：保留完整報表，但不呼叫 Judge
    SKIP_INSIGHT = True          # 手動模板驗證先略過洞察，避免額外 token
    INPUT_TOKEN_PRICE = 0.000001
    OUTPUT_TOKEN_PRICE = 0.000006
    JUDGE_INPUT_TOKEN_PRICE = None   # 未設定時不推測 Judge 成本
    JUDGE_OUTPUT_TOKEN_PRICE = None
    
    evaluator = LLMAsAJudge(
        target_questions=QUESTIONS_TO_RUN,
        gen_api_mode=GEN_API_MODE,
        gen_model=GEN_MODEL,
        judge_api_mode=JUDGE_API_MODE,
        judge_model=JUDGE_MODEL,
        mode=MODE,
        input_token_price=INPUT_TOKEN_PRICE,
        output_token_price=OUTPUT_TOKEN_PRICE,
        judge_input_token_price=JUDGE_INPUT_TOKEN_PRICE,
        judge_output_token_price=JUDGE_OUTPUT_TOKEN_PRICE,
        question_file=QUESTION_FILE,
        example_file=EXAMPLE_FILE,
        skip_insight=SKIP_INSIGHT,
    )
    
    evaluator.run(only_generation=ONLY_GENERATION)
