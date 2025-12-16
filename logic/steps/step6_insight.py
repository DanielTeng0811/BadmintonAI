from utils.app_utils import log_llm_interaction
import pandas as pd
import streamlit as st

def generate_insights(client, model_choice, prompt, execution_output, summary_info):
    """
    Step 6: 生成數據洞察 (Step 5 是 UI 顯示，由 Orchestrator 處理)。
    
    Returns:
        summary_text (str)
    """
    
    analysis_context_str = ""
    
    if execution_output:
        analysis_context_str += f"--- 程式執行輸出 (Stdout) ---\n{execution_output}\n\n"

    if not summary_info:
        analysis_context_str += "AI 程式碼未產生任何可供分析的摘要變數。"
    else:
        analysis_context_str += "程式碼執行後，擷取出以下核心變數與其值：\n\n"
        for name, val in summary_info.items():
            analysis_context_str += f"### 變數 `{name}` (型別: `{type(val).__name__}`)\n"
            if isinstance(val, (pd.DataFrame, pd.Series)):
                analysis_context_str += f"```markdown\n{val.to_markdown()}\n```\n\n"
            else:
                analysis_context_str += f"```\n{str(val)}\n```\n\n"
    
    insight_prompt = f"""
    你是羽球教練。問題: "{prompt}"
    數據:
    {analysis_context_str}
    規定:
    1. 若圖表含 "player_type"/"opponent_type"，必須輸出 Mapping: 1:發短球, 2:發長球, 3:長球, 4:殺球, 5:切球, 6:挑球, 7:平球, 8:網前球, 9:推撲球, 10:接殺防守, 11:接不到。
    2. 若圖表含 "area" (landing_area...)，必須輸出:
| Row/Col | Col A (Left) | Col B (C-Left) | Col C (C-Right) | Col D (Right) |
| :--- | :---: | :---: | :---: | :---: |
| **Row 6 (Front)** | 21 | 22 | 23 | 24 |
| **Row 5 (Front)** | 17 | 18 | 19 | 20 |
| **Row 4 (Mid)** | 13 | 14 | 15 | 16 |
| **Row 3 (Mid)** | 9 | 10 | 11 | 12 |
| **Row 2 (Mid)** | 5 | 6 | 7 | 8 |
| **Row 1 (Back)** | 1 | 2 | 3 | 4 |

    用教練口吻，基於數據精簡提供戰術洞察。說明數字背後的意義，只說事實。
    """
    
    messages_6 = [
            {"role": "system", "content": "你是一位專業羽球教練與數據戰術大師。請針對使用者問題與核心數據結果，用教練的口吻撰寫精準的戰術洞察，提供有深度的分析，需精簡回答。"},
            {"role": "user", "content": insight_prompt},
        ]
    
    try:
        insight = client.chat.completions.create(
            model=model_choice,
            messages=messages_6,
            temperature=0.4,
        )
        summary_text = insight.choices[0].message.content
        log_llm_interaction("Step 6: Insight Generation", messages_6, summary_text)
    except Exception as e:
        summary_text = f"*(無法生成洞察: {e})*"
        
    return summary_text
