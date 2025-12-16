from utils.app_utils import log_llm_interaction
import json

def enhance_prompt(client, model_choice, prompt):
    """
    Step 1: 轉化使用者問題為精準的 Enhanced Prompt。
    
    Returns:
        enhanced_prompt (str)
        relevant_topics (list)
        needs_court_info (bool)
        raw_content (str) - 用於日誌或顯示
    """
    
    enhancement_system_prompt = f"""
    你是資料分析輔助系統。請分析使用者問題：
    1. 將簡短問題轉化為精準完整的數據分析問題 (Enhanced Prompt)，勿過度詮釋，用繁體中文。
    2. 主題判斷 (Topics): 判斷問題涉及哪些面向，以決定需載入的資料欄位。
       - "spatial": 涉及座標 (x,y)、區域 (area)、落點、移動距離、站位。
       - "score": 涉及得分原因 (win_reason)、失分原因 (lose_reason)、分數狀態 (score)。
       - 若不確定，請列入。若僅需基礎資訊 (rally, player, type)，則留空列表。
    3. 場地資訊 (Needs Court Info): 若涉及 spatial 主題，通常為 true。

    輸出 JSON (No Markdown):
    {{
        "enhanced_prompt": "完整的問題",
        "relevant_topics": ["spatial", "score"],
        "needs_court_info": true
    }}
    """
    
    messages_1 = [
            {"role": "system", "content": enhancement_system_prompt},
            {"role": "user", "content": prompt}
        ]
    enhancement_response = client.chat.completions.create(
        model=model_choice,
        messages=messages_1,
        temperature=0.2
    )
    
    # 解析回應
    raw_content = enhancement_response.choices[0].message.content.strip()
    log_llm_interaction("Step 1: Enhancement", messages_1, raw_content)
    enhanced_prompt = raw_content
    needs_court_info = False

    try:
        # 嘗試移除 Markdown 標記
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
        relevant_topics = parsed.get("relevant_topics", ["spatial", "score"]) # Default safe
    except:
        print(f"Enhancement JSON parse failed, using raw text. Content: {raw_content[:50]}...")
        enhanced_prompt = raw_content
        # Fallback: 關鍵字偵測
        relevant_topics = []
        if any(k in prompt for k in ["落點", "位置", "區域", "座標", "location", "area", "distance"]):
            relevant_topics.append("spatial")
            needs_court_info = True
        if any(k in prompt for k in ["得分", "失分", "原因", "reason", "score"]):
            relevant_topics.append("score")
        if not relevant_topics: relevant_topics = ["spatial", "score"] # Safe fallback
        
    return enhanced_prompt, relevant_topics, needs_court_info, raw_content
