from utils.app_utils import log_llm_interaction
import json

def check_clarification(client, model_choice, prompt, data_schema_info, enable_clarification):
    """
    Step 0: 檢查問題是否明確 (含球員/時間/比較對象)。無法判斷則回傳 JSON 請求澄清。
    
    Returns:
       clarification_data (dict or None): 如果需要澄清，回傳包含 question 和 options 的字典，否則 None
    """
    
    # 基本判斷：如果 prompt 包含 "補充說明:", 通常是被動跳過，這裡預設調用者已處理
    # 但如果這是全新問題，仍需檢查
    
    if not enable_clarification:
        return None

    # 如果已經是回應澄清的內容 (含 "補充說明:")，則跳過檢查
    if "補充說明:" in prompt:
         return None

    clarification_check_prompt = f"""
    檢查問題是否明確 (含球員/時間/比較對象)。無法判斷則回傳 JSON 請求澄清。
    問題: "{prompt}"
    欄位: {data_schema_info}
    輸出: "CLEAR" 或 JSON:
    {{
    "need_clarification": true,
    "question": "請問您要...",
    "options": ["選項1...", "選項2..."]
    }}
    """

    messages_0 = [{"role": "user", "content": clarification_check_prompt}]
    clarification_response = client.chat.completions.create(
        model=model_choice,
        messages=messages_0,
        temperature=0.3
    )
    clarification_content = clarification_response.choices[0].message.content.strip()
    log_llm_interaction("Step 0: Clarification Check", messages_0, clarification_content)

    # 檢查是否需要澄清
    if "CLEAR" not in clarification_content:
        try:
            # 提取 JSON
            json_str = clarification_content
            if "```json" in clarification_content:
                start = clarification_content.find("```json") + 7
                end = clarification_content.find("```", start)
                json_str = clarification_content[start:end].strip()
            elif "```" in clarification_content:
                start = clarification_content.find("```") + 3
                end = clarification_content.find("```", start)
                json_str = clarification_content[start:end].strip()

            clarification_data = json.loads(json_str)

            if clarification_data.get("need_clarification"):
                return clarification_data

        except json.JSONDecodeError:
            # JSON 解析失敗，繼續正常流程
            pass
            
    return None
