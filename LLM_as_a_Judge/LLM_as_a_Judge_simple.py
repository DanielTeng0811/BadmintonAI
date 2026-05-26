import matplotlib
matplotlib.use('Agg')  # 使用非互動式後端，不會彈出圖表視窗
import os
import sys
import json
import io
import re
import base64
import time
import logging
import warnings
from datetime import datetime

import pandas as pd
import matplotlib.pyplot as plt
plt.show = lambda *args, **kwargs: None
import seaborn as sns

# 靜音 Streamlit 的內部警告與日誌錯誤
logging.getLogger("streamlit").setLevel(logging.ERROR)
os.environ["STREAMLIT_LOG_LEVEL"] = "error"
os.environ["STREAMLIT_SERVER_STATE_STORAGE"] = "memory"
warnings.filterwarnings("ignore", category=UserWarning, module="streamlit")
logging.getLogger("streamlit.runtime.scriptrunner_utils.script_run_context").disabled = True
logging.getLogger("streamlit.runtime.caching.cache_data_api").disabled = True

from dotenv import load_dotenv

# 加入父目錄到 sys.path
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# 導入 BadmintonAI 核心模組
from config.prompts import create_system_prompt, create_insight_prompt
from utils.data_loader import load_all_data
from utils.ai_client import initialize_client
from utils.analysis_workflow import (
    run_code_generation,
    run_code_execution_loop,
    run_insight_generation
)
from utils.paths import COURT_PLACE_FILE
from judge_prompt import create_judge_prompt

# 載入環境變數
env_path = os.path.join(parent_dir, '.env')
load_dotenv(dotenv_path=env_path)


class LLMAsAJudgeSimple:
    """
    【對照組 (Baseline)】簡化版評估器。
    
    流程：直接程式碼生成 -> 執行 -> 產生洞察
    與 LLM_as_a_Judge.py 的核心差異：
    1. 跳過 Step 1 (提問優化 & 欄位群組決策)
    2. 跳過欄位動態剪裁 (Dual Clipping)
    3. 直接將原始問題 + 完整 Schema + 完整欄位定義 傳給 LLM
    """

    def __init__(self, target_questions=[1],
                 gen_api_mode='OpenAI 官方', gen_model='gpt-4o',
                 judge_api_mode='OpenAI 官方', judge_model='gpt-4o',
                 question_file="評估問題.txt",
                 example_file="example.ipynb"):
        self.target_questions = target_questions
        self.gen_api_mode = gen_api_mode
        self.gen_model = gen_model
        self.judge_api_mode = judge_api_mode
        self.judge_model = judge_model
        self.question_file = question_file
        self.example_file = example_file
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._current_q_num = None

        # 設置輸出路徑
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.base_output_dir = os.path.join(script_dir, "eval_results_simple")
        self.run_dir = os.path.join(self.base_output_dir, f"run_{self.timestamp}")
        self.plots_dir = os.path.join(self.run_dir, "plots")
        os.makedirs(self.plots_dir, exist_ok=True)

        self.csv_file = os.path.join(self.run_dir, "eval_results.csv")
        self.ipynb_file = os.path.join(self.run_dir, "eval_notebook.ipynb")

        # 初始化 API
        print("🔧 正在初始化 生成 API Client...")
        _key_map = {"Claude": "ANTHROPIC_API_KEY", "Gemini": "GEMINI_API_KEY"}
        gen_api_key = os.getenv(_key_map.get(gen_api_mode, "OPENAI_API_KEY"))
        self.gen_client = initialize_client(gen_api_mode, gen_api_key)

        print("⚖️ 正在初始化 裁判 API Client...")
        judge_api_key = os.getenv(_key_map.get(judge_api_mode, "OPENAI_API_KEY"))
        self.judge_client = initialize_client(judge_api_mode, judge_api_key)

        # 載入數據 (完整 Schema + 完整欄位定義，不做過濾)
        print("📦 正在載入羽球數據...")
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
        self.reference_answers = self._load_reference_answers_with_duplicates()

        # Token 累計計數器
        self.total_pipeline_tokens = 0
        self.total_judge_tokens = 0
        self.flagged_questions = []

    def _load_reference_answers(self):
        """從 example.ipynb 載入各題標準答案，回傳 dict {q_num: code_str}"""
        example_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), self.example_file)
        if not os.path.exists(example_path):
            return {}
        try:
            with open(example_path, "r", encoding="utf-8") as f:
                nb = json.load(f)
            ref_dict = {}
            current_q_num = None
            for cell in nb["cells"]:
                content = "".join(cell["source"]).strip()
                if cell["cell_type"] == "markdown":
                    match = re.match(r'^\s*(\d+)\.\s*', content)
                    if match:
                        current_q_num = int(match.group(1))
                elif cell["cell_type"] == "code" and current_q_num is not None:
                    if current_q_num not in ref_dict:
                        ref_dict[current_q_num] = content
                        current_q_num = None
            return ref_dict
        except Exception as e:
            print(f"⚠️ 載入範例失敗: {e}")
            return {}

    def _load_reference_answers_with_duplicates(self):
        """從 example.ipynb 載入各題標準答案，支援同題號多個 code cell。"""
        example_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), self.example_file)
        if not os.path.exists(example_path):
            return {}
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
            print(f"?? 頛蝭?憭望?: {e}")
            return {}

    def _create_notebook_structure(self):
        return {
            "cells": [],
            "metadata": {
                "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
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
        self.notebook["cells"].append({
            "cell_type": "markdown",
            "metadata": {},
            "source": [line + "\n" for line in text.split("\n")]
        })

    def _add_notebook_code(self, code, b64_images=[]):
        cell = {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [line + "\n" for line in code.split("\n")]
        }
        for b64 in b64_images:
            cell["outputs"].append({
                "data": {"image/png": b64},
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

    def _record_question_failure(self, q_text, error, pipeline_tokens=0, code="", insight="", b64_images=None, only_generation=False):
        """記錄單題流程中斷，並保留當下已完成內容。"""
        b64_images = b64_images or []
        error_text = f"流程中斷：{type(error).__name__}: {error}"

        self.total_pipeline_tokens += pipeline_tokens

        if not only_generation:
            res_item = {
                "question_id": self._current_q_num,
                "question_text": q_text,
                "pipeline_tokens": pipeline_tokens,
                "judge_tokens": 0,
                "total_tokens": pipeline_tokens,
                "code_correct": False,
                "code_reasoning": error_text,
                "needs_review": True
            }
            self.results.append(res_item)
            if self._current_q_num not in self.flagged_questions:
                self.flagged_questions.append(self._current_q_num)

        q_header = f"## 題號 {self._current_q_num}"
        if not only_generation:
            q_header += " (*)"
        self._add_notebook_markdown(f"{q_header}\n**問題**: {q_text}")
        if code:
            self._add_notebook_code(code, b64_images)

        failure_md = f"### 執行中斷\n\n> **錯誤**: {error_text}"
        if insight:
            self._add_notebook_markdown(f"### 數據洞察\n{insight}\n\n---\n{failure_md}")
        else:
            self._add_notebook_markdown(failure_md)

    def _load_target_questions(self, filepath=None):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        filepath = filepath or self.question_file
        fullpath = os.path.join(script_dir, filepath)
        questions = []
        try:
            with open(fullpath, 'r', encoding='utf-8') as f:
                for line in f.readlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        num_str, q_text = line.split(":", 1)
                        q_num = int(num_str.strip())
                        if q_num in self.target_questions:
                            questions.append({"編號": q_num, "問題": q_text.strip()})
                    except:
                        pass
        except Exception as e:
            print(f"❌ 讀取問題檔案失敗: {e}")
        return questions

    def _run_pipeline_simple(self, prompt):
        """
        【簡化版流程】直接程式碼生成 -> 執行 -> 產生洞察
        
        - 無提問優化 (Step 1 跳過)
        - 無欄位剪裁 (Dual Clipping 跳過)
        - 完整 Schema + 完整欄位定義直接傳入
        - 包含場地資訊 (需要場地資訊由關鍵字判斷，預設傳入)
        """
        pipeline_tokens = 0
        exec_result = None

        # --- Step 1 (Baseline): 直接生成程式碼，使用完整 Schema ---
        print("▶ Step 1 [Baseline]: 直接程式碼生成 (完整 Schema，無優化)...")

        system_prompt = create_system_prompt(
            self.data_schema_info,
            self.column_definitions_info,
            self.court_place_info
        )

        gen_res = run_code_generation(self.gen_client, self.gen_model, system_prompt, prompt, [])
        code_to_execute = gen_res["code"]
        pipeline_tokens += gen_res.get("tokens", 0)

        # --- Step 2 (Baseline): 執行程式碼 ---
        print("▶ Step 2 [Baseline]: 執行程式...")
        exec_loop_res = run_code_execution_loop(
            self.gen_client, self.gen_model, code_to_execute, self.df, system_prompt, prompt,
            max_retries=3
        )
        pipeline_tokens += exec_loop_res.get("tokens", 0)
        code_to_execute = exec_loop_res["final_code"]
        exec_result = exec_loop_res["exec_result"]

        # --- Step 3 (Baseline): 抓取圖片 ---
        final_figs = []
        summary_info = {}
        execution_output = ""

        if exec_result:
            final_figs = exec_result.get("figs", [])
            summary_info = exec_result.get("summary_info", {})
            execution_output = exec_result.get("stdout", "")

        b64_images = []
        plot_paths = []
        for i, fig in enumerate(final_figs):
            if fig is None or not hasattr(fig, "savefig"):
                continue
            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=300, bbox_inches="tight")
            buf.seek(0)
            plot_filename = f"q{self._current_q_num}_plot_{i}.png"
            plot_path = os.path.join(self.plots_dir, plot_filename)
            with open(plot_path, "wb") as f_img:
                f_img.write(buf.getvalue())
            plot_paths.append(plot_path)
            b64_images.append(base64.b64encode(buf.getvalue()).decode('utf-8'))

        plt.close('all')

        # --- Step 4 (Baseline): 生成數據洞察 ---
        print("▶ Step 3 [Baseline]: 生成數據洞察...")
        if not summary_info:
            summary_info = {"提示": "AI 未輸出可供分析的變數。"}

        analysis_context_str = ""
        if execution_output:
            analysis_context_str += f"--- 程式執行輸出 (Stdout) ---\n{execution_output}\n\n"
        analysis_context_str += "程式碼執行後，擷取出以下核心變數與其值：\n"
        for name, val in summary_info.items():
            analysis_context_str += f"- 變數 `{name}`: {str(val)}\n"

        # 洞察使用原始 prompt (未優化)
        insight_prompt = create_insight_prompt(prompt, analysis_context_str)
        insight_res = run_insight_generation(
            self.gen_client, self.gen_model,
            "你是一位專業羽球教練與數據戰術大師。精簡提供戰術洞察。",
            insight_prompt
        )
        insight_text = insight_res["insight"]
        pipeline_tokens += insight_res.get("tokens", 0)

        return code_to_execute, insight_text, b64_images, plot_paths, pipeline_tokens

    def _judge_result(self, question, code, ref_codes):
        """呼叫 LLM 進行評分判斷（與原版相同）"""
        print("▶ Step 4 [Baseline]: AI 裁判正在評核 (對照標準答案)...")

        if not code:
            return {
                "code_correct": False,
                "reasoning": "未生成有效程式碼。"
            }

        judge_prompt = create_judge_prompt(question, code, self.column_definitions_info, ref_codes)
        messages = [{"role": "user", "content": judge_prompt}]
        judge_tokens = 0

        try:
            response = self.judge_client.chat.completions.create(
                model=self.judge_model,
                messages=messages,
                temperature=0.0
            )
            raw_eval = response.choices[0].message.content.strip()
            judge_tokens += getattr(response.usage, 'total_tokens', 0) if hasattr(response, 'usage') else 0

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
            return eval_dict

        except Exception as e:
            print(f"❌ 裁判評分失敗: {e}")
            return {
                "code_correct": False,
                "reasoning": f"評分解析錯誤: {e}",
                "judge_tokens": judge_tokens
            }

    def run(self, only_generation=False):
        """執行簡化版批量評估流程"""
        self.only_generation = only_generation
        questions = self._load_target_questions()
        total_items = len(questions)

        if total_items == 0:
            print("❌ 找不到目標問題，請檢查 target_questions 設定。")
            return

        print(f"\n🚀 啟動 LLM-as-a-Judge [Baseline 版本]: 生成 + 評核...")
        print(f"📌 目標題數: {total_items} 題")
        print(f"📊 生成模型: {self.gen_model} | 裁判模型: {self.judge_model}")
        print(f"⚡ 模式: 直接生成 (無提問優化 / 無欄位剪裁)")
        print(f"{'-'*50}")

        for idx, q_dict in enumerate(questions, 1):
            self._current_q_num = q_dict["編號"]
            q_text = q_dict["問題"]

            print(f"\n[{idx}/{total_items}] 處理問題 {self._current_q_num}: {q_text[:40]}...")

            code = ""
            insight = ""
            b64_images = []
            pipeline_tokens = 0
            try:
                # 執行簡化版流程
                code, insight, b64_images, plot_paths, pipeline_tokens = self._run_pipeline_simple(q_text)

                if not only_generation:
                    ref_code = self.reference_answers.get(self._current_q_num, "無標準答案")
                    if ref_code == "無標準答案":
                        print(f"⚠️ 題號 {self._current_q_num} 在 {self.example_file} 找不到標準答案，無法評估。")
                        continue
                        
                    # AI 裁判給分
                    eval_res = self._judge_result(q_text, code, ref_code)
                    judge_tokens = eval_res.get("judge_tokens", 0)

                    res_item = {
                        "question_id": self._current_q_num,
                        "question_text": q_text,
                        "pipeline_tokens": pipeline_tokens,
                        "judge_tokens": judge_tokens,
                        "total_tokens": pipeline_tokens + judge_tokens
                    }

                    self.total_pipeline_tokens += pipeline_tokens
                    self.total_judge_tokens += judge_tokens

                    code_correct = eval_res.get("code_correct", False)
                    reasoning = eval_res.get("reasoning", "")
                    
                    res_item["code_correct"] = code_correct
                    res_item["code_reasoning"] = reasoning

                    # 標記低分
                    is_flagged = not code_correct

                    res_item["needs_review"] = is_flagged
                    if is_flagged:
                        self.flagged_questions.append(self._current_q_num)

                    self.results.append(res_item)

                    status_emoji = "✅ 正確" if code_correct else "❌ 錯誤"
                    print(f"🏁 評分結果: {status_emoji}")
                    print(f"💰 消耗 Token: 產出 {pipeline_tokens:,} | 評分 {judge_tokens:,} | 總計 {pipeline_tokens + judge_tokens:,}")
                else:
                    self.total_pipeline_tokens += pipeline_tokens
                    print(f"💰 消耗 Token: 產出 {pipeline_tokens:,}")

                # 構建 IPYNB 結構
                q_header = f"## 題號 {self._current_q_num}"
                if not only_generation and self._current_q_num in self.flagged_questions:
                    q_header += " (*)"

                self._add_notebook_markdown(f"{q_header}\n**問題**: {q_text}")
                if code:
                    self._add_notebook_code(code, b64_images)

                if not only_generation:
                    status_text = "✅ 正確" if code_correct else "❌ 錯誤"
                    judge_md = "### 🤖 AI 裁判評分報告\n\n"
                    judge_md += f"#### 💻 程式碼評核: {status_text}\n> **分析意見**: {reasoning}\n\n"
                    self._add_notebook_markdown(f"### 數據洞察\n{insight}\n\n---\n{judge_md}")
                else:
                    self._add_notebook_markdown(f"### 數據洞察\n{insight}")
            except Exception as e:
                print(f"❌ 題號 {self._current_q_num} 流程中斷：{e}")
                self._record_question_failure(
                    q_text,
                    e,
                    pipeline_tokens=pipeline_tokens,
                    code=code,
                    insight=insight,
                    b64_images=b64_images,
                    only_generation=only_generation
                )
            finally:
                self._checkpoint_export()

        # Token 統計
        print(f"\n{'='*50}")
        total_tokens = self.total_pipeline_tokens + self.total_judge_tokens
        print(f"💰 總計 Token 消耗統計 ({total_items} 題):")
        print(f"  - 總計產出 Token: {self.total_pipeline_tokens:,}")
        print(f"  - 總計評分 Token: {self.total_judge_tokens:,}")
        print(f"  - 項目總計 Token: {total_tokens:,}")
        print(f"{'='*50}")

        if not only_generation and self.results:
            correct_count = sum(1 for item in self.results if item.get("code_correct", False))
            total_count = len(self.results)
            correct_ratio = correct_count / total_count if total_count > 0 else 0
            print(f" 正確比例: {correct_count}/{total_count} ({correct_ratio:.2%})")

        self._checkpoint_export()

        if not only_generation and self.flagged_questions:
            print(f"\n{'='*50}")
            print(f"發現錯誤題目 (程式碼判定不正確)")
            print(f"建議人工檢視以下題目: {', '.join(map(str, self.flagged_questions))}")
            print(f"{'='*50}")

    def _export_files(self, show_message=True):
        if not getattr(self, 'only_generation', False):
            df_res = pd.DataFrame(self.results)
            df_res.to_csv(self.csv_file, index=False, encoding='utf-8-sig')

        with open(self.ipynb_file, "w", encoding='utf-8') as f:
            json.dump(self.notebook, f, ensure_ascii=False, indent=2)

        if show_message:
            print(f"\n📂 評估流程結束，所有輸出已儲存至目錄:\n   {self.run_dir}")


if __name__ == "__main__":
    QUESTIONS_TO_RUN = list(range(1, 101))
    QUESTION_FILE = "評估問題_new.txt"
    EXAMPLE_FILE = "example_new.ipynb"

    # --- 1. 選擇生成 (Generation) 用的 API 與模型 ---
    GEN_API_MODE = "OpenAI 官方"
    GEN_MODEL = "gpt-4o"

    # --- 2. 選擇評估 (Judge) 用的 API 與模型 ---
    JUDGE_API_MODE = "OpenAI 官方"
    JUDGE_MODEL = "gpt-4o"

    # --- 3. 流程控制 ---
    ONLY_GENERATION = False  # 設定為 True 則只生成內容而不進行 AI 評分

    evaluator = LLMAsAJudgeSimple(
        target_questions=QUESTIONS_TO_RUN,
        gen_api_mode=GEN_API_MODE,
        gen_model=GEN_MODEL,
        judge_api_mode=JUDGE_API_MODE,
        judge_model=JUDGE_MODEL,
        question_file=QUESTION_FILE,
        example_file=EXAMPLE_FILE
    )

    evaluator.run(only_generation=ONLY_GENERATION)
