from utils.app_utils import log_llm_interaction
import pandas as pd
import matplotlib.pyplot as plt
import io
from contextlib import redirect_stdout
import streamlit as st
import platform
import utils.badminton_lib as lib
import seaborn as sns

def check_logic_and_fix(client, model_choice, prompt, code_to_execute, execution_output, exec_globals, df, status_updater=None):
    """
    Step 4: 邏輯反饋與修正 (Logic Reflection Loop)。
    
    Returns:
        final_code (str)
        execution_output (str)
        summary_info (dict)
        final_figs (list)
    """
    
    # --- 提取變數 (供邏輯檢查使用) ---
    ignore_list = ['df', 'pd', 'st', 'platform', 'io', 'fig', 'np', 'plt', 'sns']
    summary_info = {}
    
    created_figs = [plt.figure(n) for n in plt.get_fignums()]
    if not created_figs and "fig" in exec_globals:
            created_figs = [exec_globals["fig"]]
    
    summary_info["_generated_figures_count"] = len(created_figs)

    for name, val in exec_globals.items():
        if name.startswith('_') or name in ignore_list: continue
        try:
            if isinstance(val, type): continue

            if isinstance(val, (int, float, str, bool)):
                summary_info[name] = val
            elif isinstance(val, (pd.DataFrame, pd.Series)):
                if val.empty:
                    summary_info[name] = "⚠️ Empty DataFrame/Series (0 rows)"
                else:
                    summary_info[name] = f"DataFrame/Series with {len(val)} rows"
            elif hasattr(val, '__len__') and len(val) < 20:
                summary_info[name] = val
        except Exception:
            pass

    # --- 邏輯檢查 ---
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

    你是嚴格的「程式碼邏輯審計員 (Code Auditor)」，察覺邏輯錯誤部分詳細思考如何修改。請檢查：
    IMPORTANT: 根據"問題"程式碼是否有誤，畫出的圖表是否符合問題要求
    
    判斷:
    - 🐛 潛在邏輯問題 (Bug Check):
        - [資料完整性]: 檢查變數覆蓋、dropna不當。
        - [資料合適性]: 檢查數值合併錯誤 (如Score求和)。
        - [統計聚合]: 檢查 groupby + sum/mean 合理性。
        - [欄位正確性]: 檢查欄位選用 (如 player vs getpoint_player)。
        - [上下文]: 結果是否回答問題。
        - [其他]: 任何潛在邏輯陷阱。
    - ❌ 無資料: 變數顯示 `Empty/0 rows` 或 `_generated_figures_count`=0 且無輸出 -> FAIL
    - ⚠️ 資訊過載 (Information Overload):
        - **圓餅圖**: 根據結果若有多於兩類別皆為極小比例(如 < 5%)，**必須**將小於閾值的類別合併為「其他 (Others)」，**嚴禁直接過濾刪除**。
        - **長條圖**: 根據結果若 X 軸標籤過多導致重疊，或X軸與Y軸邏輯搞相反，**必須**重新設計圖表。
    - ✅ 通過: 資料非空且有輸出/圖表清晰 -> PASS
    
    回覆: "PASS" 或 修正後的完整程式碼 (含 ```python)。
    """
    messages_4 = [{"role": "user", "content": reflection_prompt}]
    reflection_response = client.chat.completions.create(
        model=model_choice,
        messages=messages_4,
        temperature=0.1
    )
    reflection_content = reflection_response.choices[0].message.content.strip()
    log_llm_interaction("Step 4: Logic Reflection", messages_4, reflection_content)

    final_figs = created_figs
    final_code = code_to_execute
    
    # 若未通過且有程式碼，嘗試修正
    if "PASS" not in reflection_content and "```python" in reflection_content:
        if status_updater:
            status_updater(label="Step 4/6: AI 發現資料為空或邏輯瑕疵，正在修正程式碼...", state="running")
        print(">>> Logic Refinement Triggered (Empty Data or Logic Error)")
        
        start = reflection_content.find("```python") + len("```python\n")
        end = reflection_content.rfind("```")
        new_code = reflection_content[start:end].strip()
        
        # 嘗試執行修正後的程式碼
        try:
            plt.close('all') 
            exec_globals = {
                "pd": pd, "df": df.copy(), "st": st, "platform": platform, 
                "io": io, "plt": plt, "sns": sns, "lib": lib 
            }
            f = io.StringIO()
            with redirect_stdout(f):
                exec(new_code, exec_globals)
            execution_output = f.getvalue()
            
            final_code = new_code 
            
            # 更新摘要資訊 (因為變數變了)
            summary_info = {}
            ignore_list = ['df', 'pd', 'st', 'platform', 'io', 'fig', 'np', 'plt', 'sns']
            for name, val in exec_globals.items():
                if name.startswith('_') or name in ignore_list: continue
                if isinstance(val, (int, float, str, bool)):
                    summary_info[name] = val
                elif isinstance(val, (pd.DataFrame, pd.Series)):
                        summary_info[name] = f"DataFrame/Series with {len(val)} rows"
                elif hasattr(val, '__len__') and len(val) < 20:
                    summary_info[name] = val

            final_figs = [plt.figure(n) for n in plt.get_fignums()]
            if not final_figs:
                    fig_var = exec_globals.get("fig", None)
                    if fig_var:
                        final_figs = [fig_var]
            
            summary_info["_generated_figures_count"] = len(final_figs)
            
        except Exception as logic_fix_error:
            print(f"Logic refinement failed: {logic_fix_error}")
            st.warning(f"⚠️ 嘗試優化圖表顯示時發生錯誤 ({logic_fix_error})，將顯示原始結果。")
            # 發生錯誤，回退到原始輸出 (exec_globals 可能已髒，但 output 和 fig 應保持原始狀態?)
            # 其實這裡回退比較麻煩，因為 plt 已 close。
            # 最簡單的是回傳原始的 code 和 output，但圖表可能沒了。
            # 為了簡化，若修正失敗，我們回傳原始的變數 (但圖表可能需要重新執行原始代碼才能拿回)
            # 這裡我們先不重新執行，直接回傳舊的 (圖可能遺失)
            pass

    return final_code, execution_output, summary_info, final_figs
