import pandas as pd
import io
import json
import platform
import matplotlib.pyplot as plt
import seaborn as sns
from contextlib import redirect_stdout
from datetime import datetime
from utils.paths import LLM_DEBUG_LOG, ensure_runtime_dirs

# --- 輔助函數 ---
def log_llm_interaction(step_name, messages, response_content):
    """
    將 LLM 的輸入與輸出紀錄到檔案中，方便除錯。
    """
    ensure_runtime_dirs()
    log_file = LLM_DEBUG_LOG
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*30}\n")
        f.write(f"[{timestamp}] Step: {step_name}\n")
        f.write(f"{'-'*30}\n")
        f.write("[Input Messages]:\n")
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            f.write(f"  <{role.upper()}>\n{content}\n")
        
        f.write(f"\n[Output Response]:\n{response_content}\n")
        f.write(f"{'='*30}\n")

def extract_conversation_context(messages, use_history):
    """
    從對話歷史中提取適合各階段使用的上下文。
    - step1_history: 用於問題優化階段 (僅包含優化後的問答內容)
    - step2_history_candidate: 用於程式碼生成階段 (包含優化後的提問與程式碼塊)
    """
    step1_history = []
    step2_history_candidate = []
    
    if use_history and len(messages) > 1:
        # 1. 收集有效的歷史訊息 (遇到 tracked=False 就斷掉)
        last_seen_enhanced_prompt = ""
        for m in reversed(messages[:-1]):
            # 如果遇到沒有開啟追蹤的訊息，視為斷點，停止收集更早的歷史
            if not m.get("tracked", True): 
                break
                
            if m.get("content") and "🤔" not in m.get("content", ""):
                role = m["role"]
                if role == "user":
                    step1_history.insert(0, {"role": "user", "content": m["content"]})
                    # Step 2 傳入的前文提問改使用優化後的 (若有)
                    prompt_for_step2 = last_seen_enhanced_prompt if last_seen_enhanced_prompt else m["content"]
                    step2_history_candidate.insert(0, {"role": "user", "content": prompt_for_step2})
                elif role == "assistant":
                    last_seen_enhanced_prompt = m.get("enhanced_prompt", "")
                    # Step 1 只看之前的優化問題，不看程式碼
                    step1_history.insert(0, {"role": "assistant", "content": m.get("enhanced_prompt", "AI處理完成")})
                    
                    # Step 2 只給程式碼，不給洞見文字
                    code = m.get("code_to_execute", "")
                    code_str = f"```python\n{code}\n```" if code else "(沒有生成程式碼)"
                    step2_history_candidate.insert(0, {"role": "assistant", "content": code_str})
        
        # 2. 僅保留最後 4 輪問答 (4 * 2 = 8 則訊息)
        step1_history = step1_history[-8:]
        step2_history_candidate = step2_history_candidate[-8:]
        
    return step1_history, step2_history_candidate

# --- 工作流函數 ---

def run_clarification_check(client, model, full_prompt):
    """
    Step 0: 檢查問題是否需要澄清
    """
    messages = [{"role": "user", "content": full_prompt}]
    
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.3
    )
    content = response.choices[0].message.content.strip()
    log_llm_interaction("Step 0: Clarification Check", messages, content)
    
    if "CLEAR" in content:
        return {"need_clarification": False}
    
    try:
        # 嘗試解析 JSON (處理 Markdown 區塊)
        json_str = content
        if "```json" in content:
            start = content.find("```json") + 7
            end = content.find("```", start)
            json_str = content[start:end].strip()
        elif "```" in content:
            start = content.find("```") + 3
            end = content.find("```", start)
            json_str = content[start:end].strip()
        
        return json.loads(json_str)
    except:
        return {"need_clarification": False}

def run_prompt_enhancement(client, model, system_prompt, user_prompt, history):
    """
    Step 1: 轉化與優化使用者問題
    """
    messages = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_prompt})
    
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.2
    )
    
    raw_content = response.choices[0].message.content.strip()
    tokens = getattr(response.usage, 'total_tokens', 0) if hasattr(response, 'usage') else 0
    log_llm_interaction("Step 1: Enhancement", messages, raw_content)
    
    # 解析 JSON
    enhanced_prompt = raw_content
    needs_court_info = False
    is_related_to_previous_code = False
    required_column_groups = []
    
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
        is_related_to_previous_code = parsed.get("is_related_to_previous_code", False)
        required_column_groups = parsed.get("required_column_groups", [])
    except:
        # 備援邏輯：如果解析失敗，根據關鍵字判斷
        if any(k in user_prompt for k in ["落點", "位置", "區域", "座標", "location", "area"]):
            needs_court_info = True
            
    return {
        "enhanced_prompt": enhanced_prompt,
        "needs_court_info": needs_court_info,
        "is_related": is_related_to_previous_code,
        "required_column_groups": required_column_groups,
        "tokens": tokens
    }

def run_code_generation(client, model, system_prompt, enhanced_prompt, history):
    """
    Step 2: 生成分析程式碼
    """
    conversation = [{"role": "system", "content": system_prompt}]
    if history:
        conversation.extend(history)
    conversation.append({"role": "user", "content": enhanced_prompt})
    
    response = client.chat.completions.create(
        model=model,
        messages=conversation
    )
    ai_response = response.choices[0].message.content
    tokens = getattr(response.usage, 'total_tokens', 0) if hasattr(response, 'usage') else 0
    log_llm_interaction("Step 2: Code Generation", conversation, ai_response)
    
    code = None
    if "```python" in ai_response:
        start = ai_response.find("```python") + len("```python\n")
        end = ai_response.rfind("```")
        code = ai_response[start:end].strip()
    
    return {"code": code, "tokens": tokens, "raw_response": ai_response}

def run_code_execution(code, df, extended_globals=None):
    """
    Step 3: 執行程式碼並收集結果
    """
    # 字體設定
    font_setup = """
import platform as _plat
import matplotlib.pyplot as plt

_sys = _plat.system()
if _sys == 'Darwin':
    plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'PingFang TC', 'Heiti TC']
elif _sys == 'Windows':
    plt.rcParams['font.sans-serif'] = ['Microsoft JhengHei', 'SimHei', 'Arial']
else:
    plt.rcParams['font.sans-serif'] = ['WenQuanYi Zen Hei', 'AR PL UMing CN']

plt.rcParams['axes.unicode_minus'] = False
"""
    plt.close('all')
    exec_globals = {
        "pd": pd, 
        "df": df.copy(), 
        "platform": platform, 
        "io": io, 
        "plt": plt,
        "sns": sns 
    }
    if extended_globals:
        exec_globals.update(extended_globals)
        
    
    f = io.StringIO()
    success = False
    error_msg = ""
    stdout = ""
    
    try:
        with redirect_stdout(f):
            exec(font_setup + "\n" + code, exec_globals)
        stdout = f.getvalue()
        success = True
    except Exception as e:
        error_msg = str(e)
        
    # 提取生成的圖表
    figs = [plt.figure(n) for n in plt.get_fignums()]
    if not figs and "fig" in exec_globals:
        figs = [exec_globals["fig"]]
        
    # 提取摘要變數 (複製原本的變數擷取邏輯)
    summary_info = {"_generated_figures_count": len(figs)}
    ignore_list = ['df', 'pd', 'platform', 'io', 'fig', 'plt', 'sns', '_sys', '_plat', 'st', 'np']
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
        except: pass
        
    return {
        "success": success,
        "error": error_msg,
        "stdout": stdout,
        "figs": figs,
        "summary_info": summary_info
    }

def run_code_execution_loop(client, model, code, df, system_prompt, enhanced_prompt, max_retries=3, status_callback=None, extended_globals=None):
    """
    Step 3 (Loop): 執行程式碼並在失敗時自動透過 AI 修復。
    """
    code_to_execute = code
    retry_count = 0
    total_tokens = 0
    success = False
    exec_result = None
    
    while retry_count <= max_retries:
        exec_result = run_code_execution(code_to_execute, df, extended_globals)
        
        if exec_result["success"]:
            success = True
            break
        else:
            retry_count += 1
            if retry_count > max_retries:
                break
                
            if status_callback:
                status_callback(f"Step 3/6: 程式執行錯誤，AI 正在修復語法 (嘗試 {retry_count}/{max_retries})...")
            
            # 錯誤反饋並重新生成
            fix_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": enhanced_prompt},
                {"role": "assistant", "content": f"```python\n{code_to_execute}\n```"},
                {"role": "user", "content": f"執行錯誤: {exec_result['error']}。請修正並重新輸出完整程式碼 (包含必要的 import)。"}
            ]
            
            response = client.chat.completions.create(model=model, messages=fix_messages)
            fix_content = response.choices[0].message.content
            total_tokens += getattr(response.usage, 'total_tokens', 0) if hasattr(response, 'usage') else 0
            log_llm_interaction(f"Step 3: Fix Loop (Retry {retry_count})", fix_messages, fix_content)
            
            if "```python" in fix_content:
                s = fix_content.find("```python") + 9
                e = fix_content.rfind("```")
                code_to_execute = fix_content[s:e].strip()

    return {
        "final_code": code_to_execute,
        "exec_result": exec_result,
        "tokens": total_tokens,
        "success": success
    }

def run_logic_reflection(client, model, full_prompt):
    """
    Step 4: 邏輯反饋與修正
    """
    messages = [{"role": "user", "content": full_prompt}]
    
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.1
    )
    content = response.choices[0].message.content.strip()
    tokens = getattr(response.usage, 'total_tokens', 0) if hasattr(response, 'usage') else 0
    log_llm_interaction("Step 4: Logic Reflection", messages, content)
    
    new_code = None
    if "```python" in content:
        start = content.find("```python") + len("```python\n")
        end = content.rfind("```")
        new_code = content[start:end].strip()
        
    return {"new_code": new_code, "tokens": tokens}

def run_insight_generation(client, model, system_prompt, full_prompt):
    """
    Step 6: 生成數據洞察
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": full_prompt},
    ]
    
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.4,
    )
    insight = response.choices[0].message.content
    tokens = getattr(response.usage, 'total_tokens', 0) if hasattr(response, 'usage') else 0
    log_llm_interaction("Step 6: Insight Generation", messages, insight)
    
    return {"insight": insight, "tokens": tokens}
