import streamlit as st
from config.prompts import create_system_prompt
from utils.data_loader import get_filtered_schema_string
from utils.app_utils import log_llm_interaction, load_court_info

def generate_code(client, model_choice, enhanced_prompt, data_schema_info, relevant_topics, needs_court_info, use_history):
    """
    Step 2: 根據 Enhanced Prompt 生成分析程式碼。
    
    Returns:
        code_to_execute (str or None)
        conversation (list) - 完整的對話紀錄，供後續修正使用
    """
    
    court_place_info = load_court_info()
    
    # [Dynamic Schema Injection]: 根據 Topics 載入對應欄位
    dynamic_col_defs = get_filtered_schema_string(relevant_topics)
    system_prompt = create_system_prompt(data_schema_info, dynamic_col_defs)
    
    # 動態注入場地資訊
    if needs_court_info and court_place_info:
        system_prompt += f"\n\n**場地位置參考資訊 (Court Grid Definitions):**\n{court_place_info}\n"

    # [視覺化指導原則]
    system_prompt += """
    \n**最佳實踐:**
    1. 區分連續數值(Float)與類別。座標勿直接 groupby。
    2. 軸標籤避免大量浮點數。
    3. 繪圖前檢查 `if len(filtered_df) > 0:`。
    """

    conversation = [{"role": "system", "content": system_prompt}]
    
    # [加入歷史訊息]
    if use_history and len(st.session_state.messages) > 1:
        valid_history = []
        # 從倒數第二則訊息開始往回看 (排除當前最新訊息)
        for m in reversed(st.session_state.messages[:-1]):
            if not m.get("tracked", True): 
                break
                
            if m.get("content") and "🤔" not in m.get("content", ""):
                valid_history.insert(0, {"role": m["role"], "content": m["content"]})
        
        # 僅保留最後 4 輪
        recent_history = valid_history[-8:]
        conversation.extend(recent_history)
    
    conversation.append({"role": "user", "content": enhanced_prompt})

    response = client.chat.completions.create(
        model=model_choice, messages=conversation
    )
    ai_response = response.choices[0].message.content
    log_llm_interaction("Step 2: Code Generation", conversation, ai_response)

    # 取出 Python code
    code_to_execute = None
    if "```python" in ai_response:
        start = ai_response.find("```python") + len("```python\n")
        end = ai_response.rfind("```")
        code_to_execute = ai_response[start:end].strip()

    return code_to_execute, conversation
