import io
import streamlit as st
import platform
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
from contextlib import redirect_stdout
import utils.badminton_lib as lib
from utils.app_utils import log_llm_interaction

def execute_and_fix(client, model_choice, code_to_execute, df, conversation, status_updater=None):
    """
    Step 3: 執行程式碼並處理語法/執行錯誤 (Runtime Error Fix Loop)。
    
    Args:
        status_updater: 一個 callback function (func(label, state)) 用於更新 UI 狀態
    
    Returns:
        success (bool)
        final_code (str)
        execution_output (str)
        exec_globals (dict)
        last_error (Exception or None)
    """
    max_retries = 3
    retry_count = 0
    success = False
    last_error = None
    exec_globals = {}
    execution_output = ""
    
    # 迴圈: 處理語法/執行錯誤
    while retry_count <= max_retries:
        try:
            # 重要：每次執行前清除 Matplotlib 狀態
            plt.close('all')
            
            # 準備執行環境
            exec_globals = {
                "pd": pd, 
                "df": df.copy(), 
                "st": st, 
                "platform": platform, 
                "io": io, 
                "plt": plt,
                "sns": sns,
                "lib": lib 
            }
            f = io.StringIO()
            with redirect_stdout(f):
                exec(code_to_execute, exec_globals)
            execution_output = f.getvalue()
            success = True
            break 
        except Exception as e:
            retry_count += 1
            last_error = e
            
            if status_updater:
                status_updater(
                    label=f"Step 3/6: 程式執行錯誤，AI 正在修復語法 (嘗試 {retry_count}/{max_retries})...", 
                    state="running"
                )
            
            conversation.append({"role": "assistant", "content": f"```python\n{code_to_execute}\n```"})
            error_feedback = f"執行上述程式碼時發生錯誤: {str(e)}。請修正錯誤並重新輸出完整程式碼 (包含必要的 import)。"
            conversation.append({"role": "user", "content": error_feedback})
            
            correction_response = client.chat.completions.create(model=model_choice, messages=conversation)
            ai_correction = correction_response.choices[0].message.content
            log_llm_interaction(f"Step 3: Error Fix (Retry {retry_count})", conversation, ai_correction)
            
            if "```python" in ai_correction:
                start = ai_correction.find("```python") + len("```python\n")
                end = ai_correction.rfind("```")
                code_to_execute = ai_correction[start:end].strip() # 更新代碼

    return success, code_to_execute, execution_output, exec_globals, last_error
