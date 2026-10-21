import pandas as pd
import io
import json
import platform
import re
import matplotlib.pyplot as plt
import seaborn as sns
from contextlib import redirect_stdout
from datetime import datetime
from utils.paths import LLM_DEBUG_LOG, ensure_runtime_dirs
from utils.model_compat import temperature_kwargs

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

def extract_python_code_block(text):
    """
    從 LLM 回覆中抽取最後一個完整的 python fenced code block。
    這裡刻意取最後一個，避免前面是分析草稿或示意片段。
    """
    if not text:
        return None

    blocks = re.findall(r"```python\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if not blocks:
        return None

    return blocks[-1].strip()

def extract_token_usage(response):
    """
    從不同供應商回應中抽取 token 使用量。
    支援 OpenAI 相容欄位 (prompt/completion) 與部分 SDK 常見欄位 (input/output)。
    """
    usage = getattr(response, "usage", None)
    if not usage:
        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }

    def _usage_get(obj, *keys):
        for key in keys:
            if isinstance(obj, dict) and key in obj:
                value = obj.get(key)
            else:
                value = getattr(obj, key, None)
            if value is not None:
                return value
        return 0

    input_tokens = _usage_get(usage, "prompt_tokens", "input_tokens")
    output_tokens = _usage_get(usage, "completion_tokens", "output_tokens")
    total_tokens = _usage_get(usage, "total_tokens", "total_token_count")
    if not total_tokens:
        total_tokens = input_tokens + output_tokens

    return {
        "input_tokens": int(input_tokens or 0),
        "output_tokens": int(output_tokens or 0),
        "total_tokens": int(total_tokens or 0),
    }

# --- 工作流函數 ---

_COURT_DEFINITION_TERMS = (
    "前場",
    "中場",
    "後場",
    "前中後場",
    "四角",
    "兩側",
    "區域",
    "場地區域",
    "區域代碼",
    "場地編號",
)


def infer_needs_court_info(user_prompt):
    """以高信心、題號無關的語意判斷是否需要正式場地對照。"""
    prompt = str(user_prompt or "")
    if any(term in prompt for term in _COURT_DEFINITION_TERMS):
        return True
    return bool(re.search(r"\b(?:zone|area)\b", prompt, flags=re.IGNORECASE))


def _optional_json_bool(value):
    """只接受真正的 JSON boolean，避免字串 false 被當成真值。"""
    return value if isinstance(value, bool) else None

def run_clarification_check(client, model, full_prompt):
    """
    Step 0: 檢查問題是否需要澄清
    """
    messages = [{"role": "user", "content": full_prompt}]
    
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        **temperature_kwargs(model, 0.3),
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

def run_prompt_enhancement(
    client,
    model,
    system_prompt,
    user_prompt,
    history,
    output_contract_validator=None,
):
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
        **temperature_kwargs(model, 0.2),
    )
    
    raw_content = response.choices[0].message.content.strip()
    token_usage = extract_token_usage(response)
    log_llm_interaction("Step 1: Enhancement", messages, raw_content)
    
    # 解析 JSON
    enhanced_prompt = user_prompt
    needs_court_info = False
    needs_court_info_llm = None
    needs_court_info_source = "default"
    semantic_court_signal = infer_needs_court_info(user_prompt)
    parse_error = ""
    is_related_to_previous_code = False
    required_column_groups = []
    analysis_subject = ""
    analysis_unit = ""
    temporal_requirement = ""
    scoring_rule = ""
    spatial_requirement = ""
    output_contract_validation = {
        "status": "not_requested",
        "route": "existing_free_code",
        "contract": None,
        "errors": [],
    }
    
    parsed = {}
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
        if (
            output_contract_validator is not None
            and not isinstance(parsed, dict)
        ):
            raise TypeError("Step 1 JSON 根節點必須是 object")
        analysis_subject = parsed.get("analysis_subject", "")
        analysis_unit = parsed.get("analysis_unit", "")
        temporal_requirement = parsed.get("temporal_requirement", "")
        scoring_rule = parsed.get("scoring_rule", "")
        spatial_requirement = parsed.get("spatial_requirement", "")
        needs_court_info_llm = _optional_json_bool(
            parsed.get("needs_court_info")
        )
        if "needs_court_info" in parsed and needs_court_info_llm is None:
            parse_error = "needs_court_info 必須是 JSON boolean"
        related_value = _optional_json_bool(
            parsed.get("is_related_to_previous_code")
        )
        is_related_to_previous_code = (
            related_value if related_value is not None else False
        )
        required_column_groups = parsed.get("required_column_groups", [])
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        parse_error = f"{type(error).__name__}: {error}"
        if output_contract_validator is not None:
            parsed = {}

    if output_contract_validator is not None:
        output_contract_validation = output_contract_validator(
            parsed.get("output_contract")
        )

    if semantic_court_signal:
        needs_court_info = True
        needs_court_info_source = (
            "llm+semantic_guard"
            if needs_court_info_llm is True
            else "semantic_guard"
        )
    elif needs_court_info_llm is not None:
        needs_court_info = needs_court_info_llm
        needs_court_info_source = "llm"

    structured_lines = []
    if analysis_subject:
        structured_lines.append(f"- 分析主體: {analysis_subject}")
    if analysis_unit:
        structured_lines.append(f"- 統計單位: {analysis_unit}")
    if temporal_requirement:
        structured_lines.append(f"- 時序需求: {temporal_requirement}")
    if scoring_rule:
        structured_lines.append(f"- 得分口徑: {scoring_rule}")
    if spatial_requirement:
        structured_lines.append(f"- 空間需求: {spatial_requirement}")
    if required_column_groups:
        structured_lines.append(f"- 關鍵欄位群組: {', '.join(required_column_groups)}")

    if structured_lines:
        enhanced_prompt = (
            f"{user_prompt}\n\n"
            "[Step 1 結構化規格]\n"
            + "\n".join(structured_lines)
            + "\n\n"
            "請依照上述結構化規格生成程式碼"
        )
            
    normalized_result = {
        "analysis_subject": analysis_subject,
        "analysis_unit": analysis_unit,
        "temporal_requirement": temporal_requirement,
        "scoring_rule": scoring_rule,
        "spatial_requirement": spatial_requirement,
        "needs_court_info": needs_court_info,
        "is_related_to_previous_code": is_related_to_previous_code,
        "required_column_groups": required_column_groups,
        "output_contract": output_contract_validation["contract"],
    }

    return {
        "enhanced_prompt": enhanced_prompt,
        "needs_court_info": needs_court_info,
        "needs_court_info_llm": needs_court_info_llm,
        "needs_court_info_source": needs_court_info_source,
        "semantic_court_signal": semantic_court_signal,
        "parse_error": parse_error,
        "raw_response": raw_content,
        "normalized_result": normalized_result,
        "is_related": is_related_to_previous_code,
        "required_column_groups": required_column_groups,
        "analysis_subject": analysis_subject,
        "analysis_unit": analysis_unit,
        "temporal_requirement": temporal_requirement,
        "scoring_rule": scoring_rule,
        "spatial_requirement": spatial_requirement,
        "output_contract_status": output_contract_validation["status"],
        "output_contract_route": output_contract_validation["route"],
        "output_contract_errors": output_contract_validation["errors"],
        **token_usage
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
    token_usage = extract_token_usage(response)
    log_llm_interaction("Step 2: Code Generation", conversation, ai_response)
    
    code = extract_python_code_block(ai_response)
    
    return {"code": code, "raw_response": ai_response, **token_usage}

def run_code_execution(code, df, extended_globals=None):
    """
    Step 3: 執行程式碼並收集結果
    """
    def _blocked_input(*args, **kwargs):
        raise RuntimeError("禁止在自動評測流程中使用 input()；請改用 df.columns 與既有欄位自動判斷。")

    def _blocked_exit(*args, **kwargs):
        raise RuntimeError("禁止在自動評測流程中使用 exit()/quit()；請改以 print() 說明錯誤並讓程式自然結束。")

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
        "sns": sns,
        "input": _blocked_input,
        "exit": _blocked_exit,
        "quit": _blocked_exit,
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
    except BaseException as e:
        error_msg = f"{type(e).__name__}: {e}"
        
    # 提取生成的圖表，並過濾掉 None 或非 matplotlib figure 物件
    figs = [plt.figure(n) for n in plt.get_fignums()]
    if not figs and "fig" in exec_globals:
        candidate_fig = exec_globals["fig"]
        if candidate_fig is not None and hasattr(candidate_fig, "savefig"):
            figs = [candidate_fig]
    figs = [fig for fig in figs if fig is not None and hasattr(fig, "savefig")]
        
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
    total_input_tokens = 0
    total_output_tokens = 0
    total_tokens = 0
    repair_attempts = 0
    attempt_usages = []
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
                {"role": "user", "content": f"執行錯誤: {exec_result['error']}。請修正並只輸出一個完整、最終、可直接執行的 python code block；不要附加任何解釋文字，包含必要的 import。"}
            ]
            
            response = client.chat.completions.create(model=model, messages=fix_messages)
            fix_content = response.choices[0].message.content
            token_usage = extract_token_usage(response)
            repair_attempts += 1
            attempt_usages.append({
                "attempt": repair_attempts,
                **token_usage,
            })
            total_input_tokens += token_usage["input_tokens"]
            total_output_tokens += token_usage["output_tokens"]
            total_tokens += token_usage["total_tokens"]
            log_llm_interaction(f"Step 3: Fix Loop (Retry {retry_count})", fix_messages, fix_content)
            
            extracted_code = extract_python_code_block(fix_content)
            if extracted_code:
                code_to_execute = extracted_code

    return {
        "final_code": code_to_execute,
        "exec_result": exec_result,
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
        "total_tokens": total_tokens,
        "success": success,
        "repair_attempts": repair_attempts,
        "attempt_usages": attempt_usages,
    }

def run_logic_reflection(client, model, full_prompt):
    """
    Step 4: 邏輯反饋與修正
    """
    messages = [{"role": "user", "content": full_prompt}]
    
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        **temperature_kwargs(model, 0.1),
    )
    content = response.choices[0].message.content.strip()
    tokens = getattr(response.usage, 'total_tokens', 0) if hasattr(response, 'usage') else 0
    log_llm_interaction("Step 4: Logic Reflection", messages, content)
    
    new_code = extract_python_code_block(content)
        
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
        **temperature_kwargs(model, 0.4),
    )
    insight = response.choices[0].message.content
    token_usage = extract_token_usage(response)
    log_llm_interaction("Step 6: Insight Generation", messages, insight)
    
    return {"insight": insight, **token_usage}
