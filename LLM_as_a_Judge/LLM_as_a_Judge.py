import matplotlib
matplotlib.use('Agg')  # 使用非互動式後端，不會彈出圖表視窗
import os
import sys
import json
import io
import platform
import re
from contextlib import redirect_stdout
from datetime import datetime
from dotenv import load_dotenv
import pandas as pd
import matplotlib.pyplot as plt
plt.show = lambda *args, **kwargs: None
import seaborn as sns
import base64
import time

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

# 加入父目錄到 sys.path，以切換為專案根目錄的環境，並允許匯入
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# 導入 BadmintonAI 核心模組
from config.prompts import (
    create_system_prompt,
    create_enhancement_system_prompt,
    create_reflection_prompt,
    create_insight_prompt
)
from utils.data_loader import load_all_data
from utils.ai_client import initialize_client
from utils.analysis_workflow import (
    run_prompt_enhancement,
    run_code_generation,
    run_code_execution_loop,
    run_logic_reflection,
    run_insight_generation
)
from utils.paths import COURT_PLACE_FILE
from judge_prompt import create_judge_prompt

# 載入環境變數
env_path = os.path.join(parent_dir, '.env')
load_dotenv(dotenv_path=env_path)

class LLMAsAJudge:
    def __init__(self, target_questions=[1], 
                 gen_api_mode='OpenAI 官方', gen_model='gpt-4o',
                 judge_api_mode='Claude', judge_model='claude-sonnet-4-6'):
        self.target_questions = target_questions
        self.gen_api_mode = gen_api_mode
        self.gen_model = gen_model
        self.judge_api_mode = judge_api_mode
        self.judge_model = judge_model
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 設置輸出路徑 (與腳本放在同一資料夾)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.base_output_dir = os.path.join(script_dir, "eval_results")
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

        # 載入數據
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
        
        # 載入標準答案
        self.reference_answers = self._load_reference_answers_with_duplicates()
        
        # Token 累計計數器
        self.total_pipeline_tokens = 0
        self.total_judge_tokens = 0
        self.flagged_questions = [] # 儲存低分標註的題號

    def _load_reference_answers(self):
        """從 example.ipynb 載入各題標準答案，回傳 dict {q_num: code_str}"""
        example_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "example.ipynb")
        if not os.path.exists(example_path):
            print("⚠️ 找不到 example.ipynb，無法進行標準答案比對。")
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
        example_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "example.ipynb")

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
            print(f"?? 頛璅?蝑?憭望?: {e}")
            return {}

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

    def _add_notebook_code(self, code, b64_images=[]):
        source = [line + "\n" for line in code.split("\n")]
        cell = {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": source
        }
        
        # 插入圖片輸出
        for b64 in b64_images:
            cell["outputs"].append({
                "data": {
                    "image/png": b64
                },
                "metadata": {},
                "output_type": "display_data"
            })
            
        self.notebook["cells"].append(cell)

    def _load_target_questions(self, filepath="評估問題.txt"):
        """讀取問題集並篩選出 target_questions 中的問題 (保證與腳本在同一資料夾)"""
        script_dir = os.path.dirname(os.path.abspath(__file__))
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

    def _parse_analysis_report(self, filepath="分析報告.md"):
        """解析 Markdown 報告中的問題、程式碼與洞察 (格式參考 front_page.py)"""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        fullpath = os.path.join(script_dir, filepath)
        
        if not os.path.exists(fullpath):
            print(f"❌ 找不到分析報告檔案: {fullpath}")
            return []
            
        with open(fullpath, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # 以使用者提問作為區塊分割點
        sections = re.split(r'### 👤 使用者提問', content)
        parsed_results = []
        
        for section in sections[1:]: #
            # 1. 提取問題 (就在分隔點後的第一行)
            q_lines = section.strip().split('\n')
            question = q_lines[0].strip() if q_lines else ""
            
            # 2. 提取程式碼 (找 Python code block)
            code_match = re.search(r'```python\n(.*?)\n```', section, re.DOTALL)
            code = code_match.group(1).strip() if code_match else ""
            
            # 3. 提取數據洞察 (### 📊 數據洞察 之後的內容)
            insight_match = re.search(r'### 📊 數據洞察\n(.*?)(?=\n\*|\n---|#|$)', section, re.DOTALL)
            insight = insight_match.group(1).strip() if insight_match else ""
            
            if question:
                parsed_results.append({
                    "question": question,
                    "code": code,
                    "insight": insight
                })
                
        print(f"🔍 解析完成，自「{filepath}」中提取到 {len(parsed_results)} 組對話。")
        return parsed_results

    def _run_pipeline(self, prompt, skip_logic_reflection=False):
        """執行 BadmintonAI 的核心邏輯 (與 front_page.py / analysis_workflow 同步)"""
        
        # --- Step 1: 轉化與優化使用者問題 ---
        print("▶ Step 1: 分析與優化問題...")
        pipeline_tokens = 0
        enhancement_system_prompt = create_enhancement_system_prompt()
        enhance_res = run_prompt_enhancement(self.gen_client, self.gen_model, enhancement_system_prompt, prompt, [])
        enhanced_prompt = enhance_res["enhanced_prompt"]
        needs_court_info = enhance_res["needs_court_info"]
        required_column_groups = enhance_res.get("required_column_groups", [])
        pipeline_tokens += enhance_res.get("tokens", 0)
        
        # --- Step 2: 生成分析程式碼 ---
        print("▶ Step 2: 生成程式碼...")
        from utils.data_loader import filter_schema_and_definitions
        filtered_schema, filtered_defs = filter_schema_and_definitions(
            required_column_groups, 
            self.data_schema_info, 
            self.column_definitions_info
        )
        system_prompt = create_system_prompt(
            filtered_schema, 
            filtered_defs, 
            self.court_place_info if needs_court_info else None
        )
        gen_res = run_code_generation(self.gen_client, self.gen_model, system_prompt, enhanced_prompt, [])
        code_to_execute = gen_res["code"]
        pipeline_tokens += gen_res.get("tokens", 0)
        
        # --- Step 3: 執行程式碼並在失敗時自動透過 AI 修復 ---
        print("▶ Step 3: 執行程式...")
        
        exec_loop_res = run_code_execution_loop(
            self.gen_client, self.gen_model, code_to_execute, self.df, system_prompt, enhanced_prompt,
            max_retries=3
        )
        pipeline_tokens += exec_loop_res.get("tokens", 0)
        
        code_to_execute = exec_loop_res["final_code"]
        exec_result = exec_loop_res["exec_result"]
        
        # 如果執行成功，判斷是否略過邏輯審查 (Step 4)
        if not skip_logic_reflection:
            print("▶ Step 4: 邏輯審查...")
            if exec_loop_res["success"] and exec_result:
                summary_info = exec_result["summary_info"]
                execution_output = exec_result["stdout"]
                
                reflection_context = "\n".join([f"{k}: {v}" for k, v in summary_info.items()])
                if not reflection_context:
                    reflection_context = "(無特定輸出變數，指沒有計算出任何數據)"
                    
                reflection_prompt = create_reflection_prompt(enhanced_prompt, code_to_execute, execution_output, reflection_context)
                
                ref_res = run_logic_reflection(self.gen_client, self.gen_model, reflection_prompt)
                pipeline_tokens += ref_res.get("tokens", 0)
                
                if ref_res["new_code"]:
                    print("-> 發現邏輯瑕疵，重新執行 AI 自主修正代碼...")
                    code_to_execute = ref_res["new_code"]
                    # 再次執行修正後的代碼 (不再進入重試迴圈)
                    from utils.analysis_workflow import run_code_execution
                    exec_result = run_code_execution(code_to_execute, self.df)
        else:
            print("▶ Step 4: 略過邏輯審查...")
                
        # 抓取最終產生的圖片
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
            
            # 存成實體檔案
            plot_filename = f"q{self._current_q_num}_plot_{i}.png"
            plot_path = os.path.join(self.plots_dir, plot_filename)
            with open(plot_path, "wb") as f_img:
                f_img.write(buf.getvalue())
            plot_paths.append(plot_path)
            
            # 轉 Base64 (For IPYNB)
            b64_images.append(base64.b64encode(buf.getvalue()).decode('utf-8'))
            
        plt.close('all') # 清除記憶體
        
        # --- Step 5: 生成數據洞察 ---
        print("▶ Step 5: 生成數據洞察...")
        if not summary_info:
            summary_info = {"提示": "AI 未輸出可供分析的變數。"}
            
        analysis_context_str = ""
        if execution_output:
            analysis_context_str += f"--- 程式執行輸出 (Stdout) ---\n{execution_output}\n\n"
        analysis_context_str += "程式碼執行後，擷取出以下核心變數與其值：\n"
        for name, val in summary_info.items():
            analysis_context_str += f"- 變數 `{name}`: {str(val)}\n"
             
        insight_prompt = create_insight_prompt(enhanced_prompt, analysis_context_str)
        insight_res = run_insight_generation(
            self.gen_client, self.gen_model, 
            "你是一位專業羽球教練與數據戰術大師。精簡提供戰術洞察。", 
            insight_prompt
        )
        insight_text = insight_res["insight"]
        pipeline_tokens += insight_res.get("tokens", 0)
        
        return code_to_execute, insight_text, b64_images, plot_paths, pipeline_tokens, required_column_groups

    def _judge_result(self, question, code, ref_codes):
        """呼叫 LLM 進行評分判斷"""
        print("▶ Step 6: AI 裁判正在評核...")
        
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
            return eval_dict
            
        except Exception as e:
            print(f"❌ 裁判評分失敗: {e}")
            return {
                "code_correct": False,
                "reasoning": f"評分解析錯誤: {e}",
                "judge_tokens": judge_tokens
            }

    def run(self, skip_logic_reflection=False, only_generation=False):
        """執行完整的批量評估流程"""
        self.only_generation = only_generation
        if self.target_questions:
            # --- 生成並評估 ---
            questions = self._load_target_questions()
            total_items = len(questions)
            
            if total_items == 0:
                print("❌ 找不到目標問題，請檢查 target_questions 設定。")
                return

            print(f"\n🚀 啟動 LLM-as-a-Judge: 生成 + 評核...")
            print(f"📌 目標題數: {total_items} 題")
            print(f"📊 生成模型: {self.gen_model} | 裁判模型: {self.judge_model}\n{'-'*50}")

            for idx, q_dict in enumerate(questions, 1):
                self._current_q_num = q_dict["編號"]
                q_text = q_dict["問題"]
                
                print(f"\n[{idx}/{total_items}] 處理問題 {self._current_q_num}: {q_text[:30]}...")
                
                # 執行分析流程
                code_to_execute, insight_text, b64_images, plot_paths, pipeline_tokens, required_column_groups = self._run_pipeline(q_text, skip_logic_reflection=skip_logic_reflection)
                
                if not only_generation:
                    ref_code = self.reference_answers.get(self._current_q_num, "無標準答案")
                    if ref_code == "無標準答案":
                        print(f"⚠️ 題號 {self._current_q_num} 在 example.ipynb 找不到標準答案，無法評估。")
                        continue
                        
                    eval_res = self._judge_result(q_text, code_to_execute, ref_code)
                    judge_tokens = eval_res.get("judge_tokens", 0)

                    res_item = {
                        "question_id": self._current_q_num,
                        "question_text": q_text,
                        "pipeline_tokens": pipeline_tokens,
                        "judge_tokens": judge_tokens,
                        "total_tokens": pipeline_tokens + judge_tokens,
                        "required_groups": ", ".join(required_column_groups)
                    }

                    # 累計總 Token
                    self.total_pipeline_tokens += pipeline_tokens
                    self.total_judge_tokens += judge_tokens

                    code_correct = eval_res.get("code_correct", False)
                    reasoning = eval_res.get("reasoning", "")
                    
                    res_item["code_correct"] = code_correct
                    res_item["code_reasoning"] = reasoning

                    # 標記需要審查的題目
                    is_flagged = not code_correct
                    res_item["needs_review"] = is_flagged
                    if is_flagged:
                        self.flagged_questions.append(self._current_q_num)

                    self.results.append(res_item)
                    
                    status_emoji = "✅ 正確" if code_correct else "❌ 錯誤"
                    print(f"🏁 評分結果: {status_emoji}")
                    print(f"💰 消耗 Token: 產出 {pipeline_tokens:,} | 評分 {judge_tokens:,} | 總計 {pipeline_tokens + judge_tokens:,}")
                else:
                    # 僅生成模式
                    self.total_pipeline_tokens += pipeline_tokens
                    print(f"💰 消耗 Token: 產出 {pipeline_tokens:,}")
                
                # 構建 IPYNB 結構
                q_header = f"## 題號 {self._current_q_num}"
                if not only_generation and self._current_q_num in self.flagged_questions:
                    q_header += " (*)"
                
                group_info = f"\n> **使用的資料欄位群組**: `{', '.join(required_column_groups) if required_column_groups else '全欄位 (Fallback)'}`"
                self._add_notebook_markdown(f"{q_header}\n**問題**: {q_text}{group_info}")
                if code_to_execute:
                    self._add_notebook_code(code_to_execute, b64_images)
                
                if not only_generation:
                    status_text = "✅ 正確" if code_correct else "❌ 錯誤"
                    judge_md = f"### 🤖 AI 裁判評分報告\n\n"
                    judge_md += f"#### 💻 程式碼評核: {status_text}\n> **分析意見**: {reasoning}\n\n"
                    self._add_notebook_markdown(f"### 數據洞察\n{insight_text}\n\n---\n{judge_md}")
                else:
                    self._add_notebook_markdown(f"### 數據洞察\n{insight_text}")
                
                time.sleep(2)
        else:
            # --- 直接評核現有報告 ---
            print(f"\n🚀 啟動 LLM-as-a-Judge: 讀取分析報告.md...")
            parsed_items = self._parse_analysis_report()
            total_items = len(parsed_items)
            
            if total_items == 0:
                return

            print(f"📌 解析到 {total_items} 個待評核項目\n{'-'*50}")

            for idx, item in enumerate(parsed_items, 1):
                q_text = item["question"]
                code = item["code"]
                insight = item["insight"]
                
                print(f"\n[{idx}/{total_items}] 正在評估: {q_text[:30]}...")
                
                # 只有評分步驟，無產出 Token
                eval_res = self._judge_result(q_text, code, insight)
                judge_tokens = eval_res.get("judge_tokens", 0)
                
                # 儲存結果
                res_item = {
                    "question_id": idx,
                    "question_text": q_text,
                    "pipeline_tokens": 0,
                    "judge_tokens": judge_tokens,
                    "total_tokens": judge_tokens
                }
                
                # 累計總 Token
                self.total_judge_tokens += judge_tokens
                
                # 展開 Code Eval
                code_eval = eval_res.get("code_eval", {})
                for k, v in code_eval.items():
                    if k != "reasoning": res_item[f"code_{k}"] = v
                res_item["code_reasoning"] = code_eval.get("reasoning", "")
                
                # 展開 Insight Eval
                insight_eval = eval_res.get("insight_eval", {})
                for k, v in insight_eval.items():
                    if k != "reasoning": res_item[f"insight_{k}"] = v
                res_item["insight_reasoning"] = insight_eval.get("reasoning", "")
                
                # 檢查標註條件
                is_flagged = False
                # 條件 1: 任何小項分數 (score_*) <= 3
                for k, v in res_item.items():
                    if (k.startswith("code_score_") or k.startswith("insight_score_")) and isinstance(v, (int, float)) and v <= 3:
                        is_flagged = True
                        break
                # 條件 2: 程式碼總分 (code_total) <= 18
                if not is_flagged:
                    code_total = res_item.get("code_code_total", 20)
                    if isinstance(code_total, (int, float)) and code_total <= 18:
                        is_flagged = True
                
                res_item["needs_review"] = is_flagged
                if is_flagged:
                    self.flagged_questions.append(idx)
                    
                self.results.append(res_item)
                
                print(f"🏁 評分結果: Code {code_eval.get('code_total', 0)}/20 | Insight {insight_eval.get('insight_total', 0)}/25")
                print(f"💰 消耗 Token: 評分 {judge_tokens:,}")
                
                # 構建輸出結構
                q_header = f"## 項目 {idx}"
                if res_item.get("needs_review"):
                    q_header += " (*)"
                self._add_notebook_markdown(f"{q_header}\n**問題**: {q_text}")
                if code:
                    self._add_notebook_code(code)
                    
                judge_md = f"### 🤖 AI 裁判評分報告\n\n"
                judge_md += f"#### 💻 程式碼評核: {code_eval.get('code_total')}/20\n> **分析意見**: {code_eval.get('reasoning')}\n\n"
                judge_md += f"#### 💡 數據洞察評核: {insight_eval.get('insight_total')}/25\n> **分析意見**: {insight_eval.get('reasoning')}\n"
                
                self._add_notebook_markdown(f"### 數據洞察\n{insight}\n\n---\n{judge_md}")
                
                time.sleep(1)

        # --- 列印最終 Token 統計 ---
        if total_items > 1:
            total_tokens = self.total_pipeline_tokens + self.total_judge_tokens
            print(f"\n{'='*50}")
            print(f"💰 總計 Token 消耗統計 ({total_items} 題):")
            
            if self.target_questions:
                # 生成 + 評核模式
                print(f"  - 總計產出 Token: {self.total_pipeline_tokens:,}")
                print(f"  - 總計評分 Token: {self.total_judge_tokens:,}")
            else:
                # 純評核模式
                print(f"  - 總計評分 Token: {self.total_judge_tokens:,}")
                
            print(f"  - 項目總計 Token: {total_tokens:,}")
            print(f"{'='*50}")

        if not only_generation and self.results:
            correct_count = sum(1 for item in self.results if not item.get("needs_review", False))
            total_count = len(self.results)
            correct_ratio = correct_count / total_count if total_count > 0 else 0
            print(f" 正確比例: {correct_count}/{total_count} ({correct_ratio:.2%})")

        self._export_files()
        
        # 顯示標註題目總結
        if not only_generation and self.flagged_questions:
            print(f"\n{'='*50}")
            print(f"發現錯誤題目 (程式碼判定不正確)")
            print(f"建議人工檢視以下題目: {', '.join(map(str, self.flagged_questions))}")
            print(f"{'='*50}")

    def _export_files(self):
        """匯出 CSV, IPYNB"""
        # CSV (僅在非僅生成模式下匯出)
        if not getattr(self, 'only_generation', False):
            df_res = pd.DataFrame(self.results)
            df_res.to_csv(self.csv_file, index=False, encoding='utf-8-sig')
             
        # IPYNB
        with open(self.ipynb_file, "w", encoding='utf-8') as f:
            json.dump(self.notebook, f, ensure_ascii=False, indent=2)
         
        print(f"\n📂 評估流程結束，所有輸出已儲存至目錄:\n   {self.run_dir}")

if __name__ == "__main__":
    # QUESTIONS_TO_RUN = [1, 3] # 指定題號進行生成與評估，否則自動讀取 分析報告.md 進行評估
    QUESTIONS_TO_RUN = list(range(1, 101))
    
    # --- 1. 選擇生成 (Generation) 用的 API 與模型 ---
    # GEN_API_MODE =  "Claude"
    # GEN_MODEL = "claude-sonnet-4-6"
    GEN_API_MODE =  "OpenAI 官方"
    GEN_MODEL = "gpt-4o"
    
    # --- 2. 選擇評估 (Judge) 用的 API 與模型 ---
    JUDGE_API_MODE = "OpenAI 官方"
    JUDGE_MODEL = "gpt-4o"
    
    # --- 3. 流程控制 ---
    SKIP_LOGIC_REFLECTION = True  # 設定為 True 即可略過 Step 4 邏輯審查
    ONLY_GENERATION = False       # 設定為 True 則只生成內容而不進行 AI 評分 (也不會產出 CSV)
    
    evaluator = LLMAsAJudge(
        target_questions=QUESTIONS_TO_RUN,
        gen_api_mode=GEN_API_MODE,
        gen_model=GEN_MODEL,
        judge_api_mode=JUDGE_API_MODE,
        judge_model=JUDGE_MODEL
    )
    
    evaluator.run(
        skip_logic_reflection=SKIP_LOGIC_REFLECTION,
        only_generation=ONLY_GENERATION
    )
