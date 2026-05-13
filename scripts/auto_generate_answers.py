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
from pathlib import Path
from dotenv import load_dotenv
import matplotlib.pyplot as plt

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 導入你的 BadmintonAI 核心模組
from config.prompts import (
    create_enhancement_system_prompt,
    create_reflection_prompt,
    create_system_prompt,
)
from utils.data_loader import load_all_data
from utils.ai_client import initialize_client
from utils.paths import COURT_PLACE_FILE, EVALUATION_QUESTIONS_FILE, NOTEBOOKS_DIR, ensure_runtime_dirs
from utils.analysis_workflow import (
    run_code_execution,
    run_code_execution_loop,
    run_code_generation,
    run_logic_reflection,
    run_prompt_enhancement,
)

# 載入環境變數
load_dotenv(PROJECT_ROOT / ".env")
ensure_runtime_dirs()


class AutoQuestionAnswerer:
    """自動問答系統"""

    def __init__(self,
                 questions_file=EVALUATION_QUESTIONS_FILE,
                 output_file=NOTEBOOKS_DIR / 'question_ans_final_63to100.ipynb',
                 api_mode='OpenAI 官方',
                 model='gpt-4o'):

        self.questions_file = Path(questions_file)
        self.output_file = Path(output_file)
        self.api_mode = api_mode
        self.model = model

        # 初始化 API
        key_map = {"Claude": "ANTHROPIC_API_KEY", "Gemini": "GEMINI_API_KEY"}
        api_key = os.getenv(key_map.get(api_mode, "OPENAI_API_KEY"))
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
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_file, 'w', encoding='utf-8') as f:
            json.dump(self.notebook, f, ensure_ascii=False, indent=2)
        print(f"✓ Notebook 已儲存至: {self.output_file}")

    def _generate_code_for_question(self, prompt):
        """
        使用 BadmintonAI 主流程生成程式碼。
        """
        enhancement_result = run_prompt_enhancement(
            self.client,
            self.model,
            create_enhancement_system_prompt(),
            prompt,
            history=[],
        )
        enhanced_prompt = enhancement_result["enhanced_prompt"]
        needs_court_info = enhancement_result["needs_court_info"]

        system_prompt = create_system_prompt(
            self.data_schema_info,
            self.column_definitions_info,
            self.court_place_info if needs_court_info else None,
        )
        generation_result = run_code_generation(
            self.client,
            self.model,
            system_prompt,
            enhanced_prompt,
            history=[],
        )

        workflow_context = {
            "enhanced_prompt": enhanced_prompt,
            "system_prompt": system_prompt,
        }
        return generation_result["code"], workflow_context

    def _execute_and_fix_code(self, code_to_execute, workflow_context, prompt):
        """
        使用主流程的受限執行環境執行程式碼並自動修復錯誤。
        """
        if not code_to_execute:
            return None

        loop_result = run_code_execution_loop(
            self.client,
            self.model,
            code_to_execute,
            self.df,
            workflow_context["system_prompt"],
            workflow_context["enhanced_prompt"],
            max_retries=3,
        )

        code_to_execute = loop_result["final_code"]
        exec_result = loop_result["exec_result"]

        if not loop_result["success"]:
            print(f"  ✗ 無法修復程式碼錯誤: {exec_result['error']}")
            return code_to_execute

        print(f"  → Step 4: 檢查邏輯正確性...")
        summary_info = exec_result["summary_info"]
        execution_output = exec_result["stdout"]

        reflection_context = "\n".join([f"{name}: {val}" for name, val in summary_info.items()])
        if not reflection_context:
            reflection_context = "(無特定輸出變數，這通常表示沒有計算出任何數據)"

        reflection_prompt = create_reflection_prompt(
            workflow_context["enhanced_prompt"],
            code_to_execute,
            execution_output,
            reflection_context,
        )
        reflection_result = run_logic_reflection(self.client, self.model, reflection_prompt)

        if reflection_result["new_code"]:
            print("  → Step 4: 發現邏輯瑕疵，正在修正...")
            new_code = reflection_result["new_code"]
            fixed_exec_result = run_code_execution(new_code, self.df)
            if fixed_exec_result["success"]:
                code_to_execute = new_code
                print("  ✓ 邏輯修正成功")
            else:
                print(f"  ⚠ 邏輯修正失敗: {fixed_exec_result['error']}，使用原始程式碼")
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

    choice = input("\n請輸入選項 (1/2/3, 預設=1): ").strip() or "1"

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
