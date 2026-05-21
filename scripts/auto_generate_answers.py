"""
完全自動化問答腳本 - 問題 63-100

這個腳本會：
1. 自動讀取問題 63-100
2. 使用你的 BadmintonAI 核心邏輯自動生成答案
3. 將結果整理成 Jupyter Notebook 格式

使用方式：
    python scripts/auto_generate_answers.py
"""

# 重要：必須在導入 matplotlib.pyplot 之前設定後端
import matplotlib
matplotlib.use('Agg')  # 使用非互動式後端，不會彈出圖表視窗

import os
import sys
import json
import io
import platform
from contextlib import redirect_stdout
from datetime import datetime
from dotenv import load_dotenv
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# 讓 scripts/ 底下的工具也能匯入專案根目錄模組
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 導入你的 BadmintonAI 核心模組
from config.prompts import create_system_prompt
from utils.data_loader import load_all_data
from utils.ai_client import initialize_client
from utils.paths import COURT_PLACE_FILE, EVALUATION_QUESTIONS_FILE, NOTEBOOKS_DIR

# 載入環境變數
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))


class AutoQuestionAnswerer:
    """自動問答系統"""

    def __init__(self,
                 questions_file=EVALUATION_QUESTIONS_FILE,
                 output_file=NOTEBOOKS_DIR / 'question_ans_final_63to100.ipynb',
                 api_mode='OpenAI 官方',
                 model='gpt-4o'):

        self.questions_file = questions_file
        self.output_file = output_file
        self.api_mode = api_mode
        self.model = model

        # 初始化 API
        _key_map = {"Claude": "ANTHROPIC_API_KEY", "Gemini": "GEMINI_API_KEY"}
        api_key = os.getenv(_key_map.get(api_mode, "OPENAI_API_KEY"))
        self.client = initialize_client(api_mode, api_key)

        # 載入數據
        print("正在載入羽球數據...")
        self.df, self.data_schema_info, self.column_definitions_info = load_all_data()

        # 載入場地資訊
        try:
            with open(COURT_PLACE_FILE, "r", encoding="utf-8") as f:
                self.court_place_info = f.read()
        except:
            self.court_place_info = ""

        # 載入問題
        self.questions = self._load_questions()

        # 建立 notebook 結構
        self.notebook = self._create_notebook_structure()

    def _load_questions(self):
        """載入問題 63-100"""
        with open(self.questions_file, 'r', encoding='utf-8') as f:
            all_questions = json.load(f)
        return [q for q in all_questions if 63 <= q['編號'] <= 100]

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

    def _add_markdown_cell(self, question_number, question_text):
        """新增 markdown cell（問題）"""
        cell = {
            "cell_type": "markdown",
            "metadata": {},
            "source": [f"第{question_number}題\n", question_text]
        }
        self.notebook["cells"].append(cell)

    def _add_code_cell(self, code_text):
        """新增 code cell（AI 生成的程式碼）"""
        code_lines = code_text.split('\n')
        source = [line + '\n' for line in code_lines[:-1]]
        if code_lines[-1]:
            source.append(code_lines[-1])

        cell = {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": source
        }
        self.notebook["cells"].append(cell)

    def _save_notebook(self):
        """儲存 notebook"""
        os.makedirs(os.path.dirname(os.fspath(self.output_file)), exist_ok=True)
        with open(self.output_file, 'w', encoding='utf-8') as f:
            json.dump(self.notebook, f, ensure_ascii=False, indent=2)
        print(f"✓ Notebook 已儲存至: {self.output_file}")

    def _generate_code_for_question(self, prompt):
        """
        使用 BadmintonAI 的邏輯生成程式碼
        這裡複製了 front_page.py 的核心邏輯
        """

        # Step 1: 轉化使用者問題
        enhancement_system_prompt = f"""
        你是資料分析輔助系統。請分析使用者問題：
        1. 將簡短問題轉化為精準完整的數據分析問題 (Enhanced Prompt)，勿過度詮釋，用繁體中文。
        2. 判斷問題是否可能用到場地資訊。若不確定，輸出true
           - 若問題可能需要用到場地資訊：前場/中場/後場、網前/底線/邊線、落點、站位、區域 (Area/Zone/Location)... -> true

        輸出 JSON (No Markdown):
        {{
            "enhanced_prompt": "完整的問題",
            "needs_court_info": true/false
        }}
        """

        messages_1 = [
            {"role": "system", "content": enhancement_system_prompt},
            {"role": "user", "content": prompt}
        ]

        enhancement_response = self.client.chat.completions.create(
            model=self.model,
            messages=messages_1,
            temperature=0.2
        )

        raw_content = enhancement_response.choices[0].message.content.strip()
        enhanced_prompt = raw_content
        needs_court_info = False

        try:
            json_str = raw_content
            if "```json" in raw_content:
                start = raw_content.find("```json") + 7
                end = raw_content.rfind("```")
                json_str = raw_content[start:end].strip()
            elif "```" in raw_content:
                start = raw_content.find("```") + 3
                end = raw_content.rfind("```")
                json_str = raw_content[start:end].strip()

            parsed = json.loads(json_str)
            enhanced_prompt = parsed.get("enhanced_prompt", raw_content)
            needs_court_info = parsed.get("needs_court_info", False)
        except:
            if any(k in prompt for k in ["落點", "位置", "區域", "座標", "location", "area"]):
                needs_court_info = True

        # Step 2: 生成分析程式碼
        system_prompt = create_system_prompt(self.data_schema_info, self.column_definitions_info)

        if needs_court_info and self.court_place_info:
            system_prompt += f"\n\n**場地位置參考資訊 (Court Grid Definitions):**\n{self.court_place_info}\n"

        system_prompt += """
        \n**最佳實踐:**
        1. 區分連續數值(Float)與類別。座標勿直接 groupby。
        2. 軸標籤避免大量浮點數。
        3. 繪圖前檢查 `if len(filtered_df) > 0:`。
        """

        conversation = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": enhanced_prompt}
        ]

        response = self.client.chat.completions.create(
            model=self.model,
            messages=conversation
        )

        ai_response = response.choices[0].message.content

        # 取出 Python code
        code_to_execute = None
        if "```python" in ai_response:
            start = ai_response.find("```python") + len("```python\n")
            end = ai_response.rfind("```")
            code_to_execute = ai_response[start:end].strip()

        return code_to_execute, conversation

    def _execute_and_fix_code(self, code_to_execute, conversation, prompt):
        """
        執行程式碼並自動修復錯誤
        完全複製 front_page.py 的 Step 3 + Step 4 邏輯
        """

        if not code_to_execute:
            return None

        # --- Step 3: 執行程式 (Runtime Error Fix Loop) ---
        max_retries = 3
        retry_count = 0
        success = False
        last_error = None
        exec_globals = {}
        execution_output = ""
        summary_info = {}

        # 迴圈 1: 處理語法/執行錯誤 (Syntax/Runtime Errors)
        while retry_count <= max_retries:
            try:
                plt.close('all')

                exec_globals = {
                    "pd": pd,
                    "df": self.df.copy(),
                    "platform": platform,
                    "io": io,
                    "plt": plt,
                    "sns": sns
                }

                f = io.StringIO()
                with redirect_stdout(f):
                    exec(code_to_execute, exec_globals)

                execution_output = f.getvalue()
                success = True
                break  # 成功執行，跳出迴圈

            except Exception as e:
                retry_count += 1
                last_error = e
                print(f"  ⚠ 執行錯誤 (嘗試 {retry_count}/{max_retries}): {str(e)[:100]}")

                conversation.append({"role": "assistant", "content": f"```python\n{code_to_execute}\n```"})
                error_feedback = f"執行上述程式碼時發生錯誤: {str(e)}。請修正錯誤並重新輸出完整程式碼 (包含必要的 import)。"
                conversation.append({"role": "user", "content": error_feedback})

                correction_response = self.client.chat.completions.create(
                    model=self.model,
                    messages=conversation
                )

                ai_correction = correction_response.choices[0].message.content

                if "```python" in ai_correction:
                    start = ai_correction.find("```python") + len("```python\n")
                    end = ai_correction.rfind("```")
                    code_to_execute = ai_correction[start:end].strip()

        if not success:
            print(f"  ✗ 無法修復程式碼錯誤: {last_error}")
            return code_to_execute

        # --- 提取變數 (供 Step 4 邏輯檢查使用) ---
        ignore_list = ['df', 'pd', 'platform', 'io', 'fig', 'np', 'plt', 'sns']

        # 檢查生成的圖表數量
        created_figs = [plt.figure(n) for n in plt.get_fignums()]
        if not created_figs and "fig" in exec_globals:
            created_figs = [exec_globals["fig"]]

        summary_info["_generated_figures_count"] = len(created_figs)

        for name, val in exec_globals.items():
            if name.startswith('_') or name in ignore_list:
                continue

            try:
                # 避免 class 物件觸發錯誤
                if isinstance(val, type):
                    continue

                if isinstance(val, (int, float, str, bool)):
                    summary_info[name] = val
                elif isinstance(val, (pd.DataFrame, pd.Series)):
                    # 強制讓 LLM 知道資料是空的
                    if val.empty:
                        summary_info[name] = "⚠️ Empty DataFrame/Series (0 rows)"
                    else:
                        summary_info[name] = f"DataFrame/Series with {len(val)} rows"
                elif hasattr(val, '__len__') and len(val) < 20:
                    summary_info[name] = val
            except Exception:
                pass

        # --- [Step 4: 邏輯反饋與修正 (Logic Reflection Loop)] ---
        print(f"  → Step 4: 檢查邏輯正確性...")

        reflection_context = ""
        for name, val in summary_info.items():
            reflection_context += f"{name}: {val}\n"

        if not reflection_context:
            reflection_context = "(無特定輸出變數，這通常表示沒有計算出任何數據)"

        reflection_prompt = f"""
        [查核資料]
        1. 問題: "{prompt}"
        2. 程式碼:
        ```python
        {code_to_execute}
        ```
        3. 執行與變數: {execution_output}
        {reflection_context}

        你是嚴格的「程式碼邏輯審計員 (Code Auditor)」。請先**逐步推理 (Chain of Thought)**，找出程式碼邏輯與使用者問題不符之處，並列出具體錯誤，最後再決定是否修正。
        **重要檢查清單:**
        - 確認程式碼是否有明確解決問題
        - 確認程式碼內部邏輯是否有誤
        - 執行結果是否合理

        **邏輯錯誤案例:**
        - 🐛 **邏輯潛在錯誤**:
            - 資料完整性: 變數是否被不當覆蓋？dropna 是否刪除了過多資料？
            - 統計正確性: groupby + sum/mean/count 是否符合題目語意？(如：求次數卻用 sum, 求總分卻用 count)
            - 欄位選用: 是否選錯欄位？ (如: player A vs player B)
        - 🎯 **意圖相符性**: 程式碼產出的圖表/數據，是否直接回答了使用者的問題？
        - ❌ **異常檢測**: 是否產生 `Empty/0 rows`？圖表是否空白 (`_generated_figures_count`=0)？
        - ⚠️ **視覺呈現**:
            - 圓餅圖: 若小於 5% 的類別過多，**必須**合併為「其他 (Others)」。
            - 長條圖: X 軸標籤若過多導致擁擠難讀，應調整為水平長條圖或篩選 Top N。
        - 時間序是否搞錯: shift()邏輯需要使用嗎?是否使用正確?
        **回覆格式 (Format):**
        請嚴格遵守以下格式回覆：

        [Reasoning]
        1. (觀察到的問題或確認正確的事實...)
        2. ...

        [Conclusion]
        (若需修正，請提供完整 Python 程式碼，包含必要的 import，並務必用 ```python 包裹)
        (若無需修正，請僅回覆單字: PASS)
        """

        messages_4 = [{"role": "user", "content": reflection_prompt}]
        reflection_response = self.client.chat.completions.create(
            model=self.model,
            messages=messages_4,
            temperature=0.1
        )
        reflection_content = reflection_response.choices[0].message.content.strip()

        if "```python" in reflection_content:
            # 觸發邏輯修正
            print("  → Step 4: 發現邏輯瑕疵，正在修正...")

            start = reflection_content.find("```python") + len("```python\n")
            end = reflection_content.rfind("```")
            new_code = reflection_content[start:end].strip()

            try:
                plt.close('all')
                # 重新初始化環境
                exec_globals = {
                    "pd": pd,
                    "df": self.df.copy(),
                    "platform": platform,
                    "io": io,
                    "plt": plt,
                    "sns": sns
                }
                f = io.StringIO()
                with redirect_stdout(f):
                    exec(new_code, exec_globals)
                execution_output = f.getvalue()

                code_to_execute = new_code
                print("  ✓ 邏輯修正成功")

            except Exception as logic_fix_error:
                print(f"  ⚠ 邏輯修正失敗: {logic_fix_error}，使用原始程式碼")
                # Fallback: 使用原始程式碼
        else:
            print("  ✓ 邏輯檢查通過")

        return code_to_execute

    def process_all_questions(self):
        """處理所有問題"""

        total = len(self.questions)
        print(f"\n{'='*70}")
        print(f"BadmintonAI 自動問答系統")
        print(f"{'='*70}")
        print(f"問題範圍: 63-100 (共 {total} 題)")
        print(f"API 模式: {self.api_mode}")
        print(f"模型: {self.model}")
        print(f"{'='*70}\n")

        for idx, question in enumerate(self.questions, 1):
            q_num = question['編號']
            q_text = question['問題']

            print(f"[{idx}/{total}] 問題 {q_num}: {q_text[:50]}{'...' if len(q_text) > 50 else ''}")

            try:
                # 新增問題到 notebook
                self._add_markdown_cell(q_num, q_text)

                # 生成程式碼
                print(f"  → 正在生成程式碼...")
                code, conversation = self._generate_code_for_question(q_text)

                if not code:
                    print(f"  ⚠ AI 未生成程式碼")
                    self._add_code_cell("# AI 未生成程式碼")
                    continue

                # 執行並修復程式碼（包含 Step 4 邏輯檢查）
                print(f"  → Step 3: 執行程式碼...")
                final_code = self._execute_and_fix_code(code, conversation, q_text)

                # 加入到 notebook
                self._add_code_cell(final_code)
                print(f"  ✓ 完成")

                # 每 5 題自動儲存
                if idx % 5 == 0:
                    self._save_notebook()
                    print(f"\n[自動儲存] 已完成 {idx}/{total} 題\n")

            except Exception as e:
                print(f"  ✗ 處理失敗: {e}")
                self._add_code_cell(f"# 處理失敗: {e}")

            # 清理 matplotlib 狀態
            plt.close('all')

        # 最終儲存
        self._save_notebook()
        print(f"\n{'='*70}")
        print(f"🎉 全部完成！共處理 {total} 個問題")
        print(f"✓ 結果已儲存至: {self.output_file}")
        print(f"{'='*70}\n")


def main():
    """主程式"""

    print("\n🏸 BadmintonAI 自動問答系統\n")

    # 選擇 API 模式
    print("請選擇 API 模式：")
    print("1. OpenAI 官方 (gpt-4o) - 推薦")
    print("2. OpenAI 官方 (gpt-4o-mini) - 較便宜")
    print("3. Gemini (gemini-2.0-flash)")
    print("4. Claude (claude-sonnet-4-6)")

    choice = input("\n請輸入選項 (1/2/3/4, 預設=1): ").strip() or "1"

    if choice == "1":
        api_mode = "OpenAI 官方"
        model = "gpt-4o"
    elif choice == "2":
        api_mode = "OpenAI 官方"
        model = "gpt-4o-mini"
    elif choice == "3":
        api_mode = "Gemini"
        model = "gemini-2.0-flash"
    elif choice == "4":
        api_mode = "Claude"
        model = "claude-sonnet-4-6"
    else:
        print("無效選項，使用預設: OpenAI 官方 (gpt-4o)")
        api_mode = "OpenAI 官方"
        model = "gpt-4o"

    print(f"\n✓ 已選擇: {api_mode} - {model}\n")

    # 確認執行
    confirm = input("確定要開始自動處理 38 個問題嗎？(y/n): ").strip().lower()
    if confirm != 'y':
        print("已取消。")
        return

    # 建立自動問答系統
    answerer = AutoQuestionAnswerer(
        api_mode=api_mode,
        model=model
    )

    # 開始處理
    answerer.process_all_questions()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n程式被中斷。")
    except Exception as e:
        print(f"\n發生錯誤：{e}")
        import traceback
        traceback.print_exc()
