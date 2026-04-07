import streamlit as st
import os
import io
import sys
from contextlib import redirect_stdout
import platform
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
import zipfile
import matplotlib.pyplot as plt # 確保 matplotlib 被導入
import seaborn as sns # 引入 seaborn 提供更多繪圖選擇，但不強制使用

# 自訂模組 (請確保 config/prompts.py 裡面沒有 circular import)
from config.prompts import (
    create_system_prompt,
    create_enhancement_system_prompt,
    create_reflection_prompt,
    create_insight_prompt,
    create_clarification_check_prompt
)
from utils.data_loader import load_all_data
from utils.ai_client import initialize_client
from utils.data_processor import process_badminton_data

# --- 字體設定 ---
_FONT_SETUP_CODE = """
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

# --- 初始設定與環境變數載入 ---
load_dotenv()

# 設定頁面
st.set_page_config(
    page_title="羽球 AI 數據分析師",
    page_icon="🏸",
    layout="wide"
)

# --- 輔助函數：安全讀取 API Key ---
def get_api_key(key_name):
    """
    從環境變數或 Streamlit Secrets 安全讀取 API Key。
    """
    # 優先從 .env 環境變數讀取
    env_value = os.getenv(key_name, "")
    if env_value:
        return env_value

    # 如果環境變數沒有，嘗試從 Streamlit Secrets 讀取
    try:
        if hasattr(st, 'secrets') and st.secrets:
            return st.secrets.get(key_name, "")
    except Exception:
        pass

    return ""

# --- 輔助函數：讀取場地定義 ---
@st.cache_data
def load_court_info():
    try:
        with open("court_place.txt", "r", encoding="utf-8") as f:
            return f.read()
        print("Court info loaded successfully")
    except:
        return ""

court_place_info = load_court_info()

# --- 輔助函數：紀錄 LLM 互動 ---
def log_llm_interaction(step_name, messages, response_content):
    """
    將 LLM 的輸入與輸出紀錄到檔案中，方便除錯。
    """
    log_file = "llm_debug_log.txt"
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

# --- 🔒 通關密碼保護 (Simple Auth) ---
# 這是為了讓 App 可公開網址 (方便分享)，但只讓知道密碼的人使用 (保護 API Key)
def check_password():
    """Returns `True` if the user had the correct password."""

    # 1. 如果已經驗證過，直接回傳 True
    if st.session_state.get("password_correct", False):
        return True

    # 2. 設定你的通關密碼 (預設: badminton2024)
    # 也可以從 Secrets 讀取: st.secrets.get("APP_PASSWORD", "badminton2024")
    CORRECT_PASSWORD = os.getenv("APP_PASSWORD", "badminton2024")

    # 3. 顯示輸入框
    st.header("🔒 請輸入通關密碼")
    st.write("此應用程式受密碼保護，以避免 API Key 被濫用。")
    password_input = st.text_input("密碼", type="password")

    if st.button("登入"):
        if password_input == CORRECT_PASSWORD:
            st.session_state["password_correct"] = True
            st.rerun() # 重新整理以進入主畫面
        else:
            st.error("❌ 密碼錯誤")
    
    return False

# 如果密碼驗證未通過，則停止執行後續程式碼
if not check_password():
    st.stop()

# --- 資料載入 ---
df, data_schema_info, column_definitions_info = load_all_data()

# --- Streamlit UI ---
st.title("🏸 羽球 AI 數據分析師")
st.markdown("#### 透過自然語言，直接生成數據分析圖表")

# 側邊欄
with st.sidebar:
    st.header("⚙️ API 設定")
    api_mode = st.selectbox("API 模式", ["Gemini", "OpenAI 官方", "交大伺服器"], index=1)
    api_key_env_var = "GEMINI_API_KEY" if api_mode == "Gemini" else "OPENAI_API_KEY"

    # 使用 get_api_key 函數安全讀取 API Key
    default_api_key = get_api_key(api_key_env_var)

    api_key_input = st.text_input(
        f"{api_mode} API Key",
        value=default_api_key,
        type="password",
        help="💡 本地開發：從 .env 讀取 | 雲端部署：從 Streamlit Secrets 讀取"
    )
    
    st.divider()
    st.header("📂 資料管理")
    uploaded_file = st.file_uploader("上傳新比賽資料 (CSV)", type=["csv"], help="上傳 raw data，系統將自動執行 data_processing 並更新資料庫")
    
    if uploaded_file is not None:
        if st.button("🚀 開始處理並載入"):
            with st.spinner("正在進行資料預處理與資料庫更新..."):
                try:
                    # 執行資料處理
                    process_badminton_data(uploaded_file)
                    
                    # 清除快取以確保載入新資料
                    st.cache_data.clear()
                    
                    st.success("✅ 資料處理完成！請稍候，頁面將自動重整...")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ 處理失敗: {e}")

    if api_mode == "Gemini":
        model_choice = st.selectbox("選擇模型",["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"], index=0)
    else:
        model_choice = st.selectbox("選擇模型", ["gpt-4o-mini", "gpt-4o"], index=1)

    st.divider()

    # --- 📊 Token 消耗儀表板 ---
    st.header("📊 Token 消耗追蹤")
    if "total_tokens" not in st.session_state:
        st.session_state.total_tokens = 0
    if "last_turn_tokens" not in st.session_state:
        st.session_state.last_turn_tokens = 0
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        metric_total = st.empty()
        metric_total.metric("累積消耗", f"{st.session_state.total_tokens:,}")
    with col_t2:
        metric_last = st.empty()
        metric_last.metric("最新一輪", f"{st.session_state.last_turn_tokens:,}")

    st.divider()

    # 多輪問答開關
    enable_clarification = st.checkbox("啟用多輪問答（問題不明確時會主動詢問）", value=False)

    st.divider()
    st.markdown("#### 範例問題")
    st.info("""
    - 球員 A 的各球種分佈是怎麼樣的？請用圓餅圖呈現。
    - 哪個落點 (`landing_zone`) 的球最常出現？請用長條圖表示。
    - 各球員 (`player`) 的殺球 (`smash`) 次數比較。
    - 誰是失誤王？請統計各球員的失誤次數。
    """)
    st.divider()

    # --- ZIP 匯出功能 (佔位符) ---
    zip_download_placeholder = st.empty()
    # 預設顯示一個 disabled 的按鈕，避免畫面閃爍或空白
    zip_download_placeholder.download_button(
        label="💾 下載分析報告 (ZIP)",
        data=b"",
        file_name="empty.zip",
        disabled=True,
        key="initial_zip_button"
    )
    st.divider()

    if st.button("🗑️ 清除對話"):
        st.session_state.messages = []
        # 清除 Token 計數器
        st.session_state.total_tokens = 0
        st.session_state.last_turn_tokens = 0
        st.rerun()

# 初始化 client 與對話
client = initialize_client(api_mode, api_key_input)
if "messages" not in st.session_state:
    st.session_state.messages = []

# 初始化多輪問答狀態
if "awaiting_clarification" not in st.session_state:
    st.session_state.awaiting_clarification = False
if "clarification_data" not in st.session_state:
    st.session_state.clarification_data = None
if "original_prompt" not in st.session_state:
    st.session_state.original_prompt = ""

# 顯示歷史
for idx, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        # [修改點]：若有優化後的提問邏輯，顯示在對話中
        if message.get("enhanced_prompt"):
            with st.expander("🧠 查看 AI 優化後的提問邏輯 (Step 1)", expanded=False):
                st.markdown(f"**優化導引 (Enhanced Prompt):**\n{message['enhanced_prompt']}")

        st.markdown(message["content"])
        figures = message.get("figures", [])
        if not figures and message.get("figure"):
            figures = [message["figure"]]

        for fig_idx, fig in enumerate(figures):
            st.pyplot(fig)
            buf = io.BytesIO()
            fig.savefig(buf, format='png', dpi=300, bbox_inches='tight')
            buf.seek(0)
            st.download_button(
                label=f"📥 下載圖表 {fig_idx + 1}",
                data=buf,
                file_name=f"羽球分析_{idx}_{fig_idx}_{datetime.now().strftime('%Y%m%d')}.png",
                mime="image/png",
                key=f"download_history_{idx}_{fig_idx}",
            )

# --- 主對話流程 ---
# 添加歷史紀錄開關
use_history = st.toggle("🔗 接續前文 (Track History)", value=False, help="開啟後，AI 將參考最近的對話紀錄來回答問題。")

if prompt := st.chat_input("請輸入你的數據分析問題..."):
    # Clear debug log on new input (create if not exists, truncate if exists)
    with open("llm_debug_log.txt", "w", encoding="utf-8") as f:
        pass # Truncate file to 0 bytes

    if df is None:
        st.error("❌ 找不到 'all_dataset.csv'。")
    elif not api_key_input:
        st.error("⚠️ 請輸入 API Key。")
    else:
        # === 處理澄清回應 ===
        skip_clarification = False
        if st.session_state.awaiting_clarification:
            # 使用者已經選擇了選項或提供補充說明
            user_answer = prompt.strip()
            clarification_data = st.session_state.clarification_data

            # 檢查是否是選項編號
            if user_answer.isdigit() and clarification_data:
                option_index = int(user_answer) - 1
                if 0 <= option_index < len(clarification_data.get('options', [])):
                    user_answer = clarification_data['options'][option_index]

            # 組合完整問題
            full_prompt = f"{st.session_state.original_prompt}\n補充說明: {user_answer}"

            # 記錄使用者的補充回應
            st.session_state.messages.append({"role": "user", "content": prompt})

            # 重置澄清狀態
            st.session_state.awaiting_clarification = False
            st.session_state.clarification_data = None

            # 使用完整問題進行分析
            prompt = full_prompt
            skip_clarification = True
        else:
            # 儲存問題與追蹤狀態
            st.session_state.messages.append({
                "role": "user", 
                "content": prompt,
                "tracked": use_history # 儲存當前是否開啟追蹤
            })

        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            # 使用 st.status 來顯示多步驟進程
            with st.status("AI 數據分析師正在處理中...") as status:
                try:
                    # --- [Step 0: 問題檢查與澄清] ---
                    if not skip_clarification and enable_clarification:
                        status.update(label="Step 0/6: 檢查問題是否需要澄清...")

                        import json
                        clarification_check_prompt = create_clarification_check_prompt(prompt, data_schema_info)

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
                                    # 設定澄清狀態
                                    st.session_state.awaiting_clarification = True
                                    st.session_state.clarification_data = clarification_data
                                    st.session_state.original_prompt = prompt

                                    # 顯示澄清問題
                                    st.markdown(f"### 🤔 {clarification_data['question']}")
                                    st.info("請在下方輸入框中選擇以下選項之一（輸入選項編號或完整描述），或直接輸入您的補充說明：")

                                    options_text = ""
                                    for i, option in enumerate(clarification_data['options'], 1):
                                        option_line = f"**{i}.** {option}"
                                        st.markdown(option_line)
                                        options_text += f"{i}. {option}\n"

                                    # 儲存助手回應到歷史
                                    clarification_msg = f"### 🤔 {clarification_data['question']}\n\n"
                                    clarification_msg += "請選擇以下選項之一，或直接提供補充說明：\n\n"
                                    clarification_msg += options_text

                                    st.session_state.messages.append({
                                        "role": "assistant",
                                        "content": clarification_msg,
                                        "figures": []
                                    })

                                    status.update(label="等待您的補充資訊...", state="complete")
                                    st.stop()

                            except json.JSONDecodeError:
                                # JSON 解析失敗，繼續正常流程
                                pass

                    # --- Token 計數器：本輪累加 ---
                    _turn_tokens = 0

                    # --- [Step 1: 轉化使用者問題] ---
                    status.update(label="Step 1/6: 正在釐清您的問題...")

                    # [新增]: 提前準備兩種歷史對話 (供 Step 1 與 Step 2 分別使用)
                    step1_history = []
                    step2_history_candidate = []
                    
                    if use_history and len(st.session_state.messages) > 1:
                        # 1. 收集有效的歷史訊息 (遇到 tracked=False 就斷掉)
                        last_seen_enhanced_prompt = ""
                        for m in reversed(st.session_state.messages[:-1]):
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

                    
                    enhancement_system_prompt = create_enhancement_system_prompt()
                    
                    messages_1 = [{"role": "system", "content": enhancement_system_prompt}]
                    
                    # [優化] Step 1 注入純文字邏輯歷史
                    if step1_history:
                        messages_1.extend(step1_history)

                    messages_1.append({"role": "user", "content": prompt})
                    enhancement_response = client.chat.completions.create(
                        model=model_choice,
                        messages=messages_1,
                        temperature=0.2
                    )
                    
                    # 解析回應
                    raw_content = enhancement_response.choices[0].message.content.strip()
                    if hasattr(enhancement_response, 'usage') and enhancement_response.usage:
                        _turn_tokens += getattr(enhancement_response.usage, 'total_tokens', 0)
                    log_llm_interaction("Step 1: Enhancement", messages_1, raw_content)
                    enhanced_prompt = raw_content
                    needs_court_info = False
                    is_related_to_previous_code = False

                    try:
                        import json
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
                        is_related_to_previous_code = parsed.get("is_related_to_previous_code", False)
                    except:
                        print(f"Enhancement JSON parse failed, using raw text. Content: {raw_content[:50]}...")
                        # Fallback: 如果解析失敗，假設不需要場地資訊，或者如果關鍵字出現則設為True
                        if any(k in prompt for k in ["落點", "位置", "區域", "座標", "location", "area"]):
                            needs_court_info = True

                    print(f"Enhanced Prompt: {enhanced_prompt}")
                    print(f"Needs Court Info: {needs_court_info}")
                    print(f"Is Related To Previous Code: {is_related_to_previous_code}")

                    # --- [Step 2: 生成分析程式碼] ---
                    status.update(label="Step 2/6: 正在生成分析程式碼...")
                    system_prompt = create_system_prompt(
                        data_schema_info, 
                        column_definitions_info, 
                        court_place_info if needs_court_info else None
                    )

                    conversation = [{"role": "system", "content": system_prompt}]
                    
                    # [優化] 只有當 Step 1 判定與上一題相關時，才將單純的程式碼歷史 (step2_history_candidate) 傳給 Step 2
                    if is_related_to_previous_code and step2_history_candidate:
                        conversation.extend(step2_history_candidate)
                    
                    conversation.append({"role": "user", "content": enhanced_prompt})

                    response = client.chat.completions.create(
                        model=model_choice, messages=conversation
                    )
                    ai_response = response.choices[0].message.content
                    if hasattr(response, 'usage') and response.usage:
                        _turn_tokens += getattr(response.usage, 'total_tokens', 0)
                    log_llm_interaction("Step 2: Code Generation", conversation, ai_response)

                    # 取出 Python code
                    code_to_execute = None
                    if "```python" in ai_response:
                        start = ai_response.find("```python") + len("```python\n")
                        end = ai_response.rfind("```")
                        code_to_execute = ai_response[start:end].strip()

                    # --- [Step 3: 執行程式 (Runtime Error Fix Loop)] ---
                    status.update(label="Step 3/6: 正在執行程式碼...")
                    
                    final_figs = []
                    summary_info = {}
                    exec_globals = {} # 初始化環境變數
                    execution_output = "" # [Fix] Ensure variable is defined even if no code is generated
                    
                    if code_to_execute:
                        max_retries = 3
                        retry_count = 0
                        success = False
                        last_error = None
                        
                        # 迴圈 1: 處理語法/執行錯誤 (Syntax/Runtime Errors)
                        while retry_count <= max_retries:
                            try:
                                # 重要：每次執行前清除 Matplotlib 狀態，避免上一張圖殘留或干擾
                                plt.close('all')
                                
                                # 準備執行環境，確保 df 存在
                                # 加入 sns 到執行環境，提供更多彈性
                                exec_globals = {
                                    "pd": pd, 
                                    "df": df.copy(), 
                                    "st": st, 
                                    "platform": platform, 
                                    "io": io, 
                                    "plt": plt,
                                    "sns": sns 
                                }
                                f = io.StringIO()
                                with redirect_stdout(f):
                                    exec(_FONT_SETUP_CODE + "\n" + code_to_execute, exec_globals)
                                execution_output = f.getvalue()
                                success = True
                                break 
                            except Exception as e:
                                retry_count += 1
                                last_error = e
                                status.update(label=f"Step 3/6: 程式執行錯誤，AI 正在修復語法 (嘗試 {retry_count}/{max_retries})...", state="running")
                                
                                conversation.append({"role": "assistant", "content": f"```python\n{code_to_execute}\n```"})
                                error_feedback = f"執行上述程式碼時發生錯誤: {str(e)}。請修正錯誤並重新輸出完整程式碼 (包含必要的 import)。"
                                conversation.append({"role": "user", "content": error_feedback})
                                
                                correction_response = client.chat.completions.create(model=model_choice, messages=conversation)
                                ai_correction = correction_response.choices[0].message.content
                                if hasattr(correction_response, 'usage') and correction_response.usage:
                                    _turn_tokens += getattr(correction_response.usage, 'total_tokens', 0)
                                log_llm_interaction(f"Step 3: Error Fix (Retry {retry_count})", conversation, ai_correction)
                                
                                if "```python" in ai_correction:
                                    start = ai_correction.find("```python") + len("```python\n")
                                    end = ai_correction.rfind("```")
                                    code_to_execute = ai_correction[start:end].strip() # 更新代碼

                        if not success:
                            raise last_error

                        # --- 提取變數 (供下一步邏輯檢查使用) ---
                        ignore_list = ['df', 'pd', 'st', 'platform', 'io', 'fig', 'np', 'plt', 'sns']
                        
                        # 檢查生成的圖表數量
                        created_figs = [plt.figure(n) for n in plt.get_fignums()]
                        if not created_figs and "fig" in exec_globals:
                             created_figs = [exec_globals["fig"]]
                        
                        summary_info["_generated_figures_count"] = len(created_figs)

                        for name, val in exec_globals.items():
                            if name.startswith('_') or name in ignore_list: continue
                            
                            try:
                                # [Fix] 避免 class 物件觸發 object of type 'type' has no len()
                                if isinstance(val, type):
                                    continue

                                if isinstance(val, (int, float, str, bool)):
                                    summary_info[name] = val
                                elif isinstance(val, (pd.DataFrame, pd.Series)):
                                    # 強制讓 LLM 知道資料是空的
                                    if val.empty:
                                        summary_info[name] = "⚠️ Empty DataFrame/Series (0 rows)"
                                    else:
                                        # 如果資料太大，只告訴 LLM 大小，不傳全部內容
                                        summary_info[name] = f"DataFrame/Series with {len(val)} rows"
                                elif hasattr(val, '__len__') and len(val) < 20:
                                    summary_info[name] = val
                            except Exception:
                                pass

                        # --- [Step 4: 邏輯反饋與修正 (Logic Reflection Loop)] ---
                        status.update(label="Step 4/6: AI 正在檢查分析結果的邏輯性...")
                        
                        reflection_context = ""
                        for name, val in summary_info.items():
                            reflection_context += f"{name}: {val}\n"
                        
                        if not reflection_context:
                            reflection_context = "(無特定輸出變數，這通常表示沒有計算出任何數據)"
                        reflection_prompt = create_reflection_prompt(
                            enhanced_prompt, code_to_execute, execution_output, reflection_context
                        )
                        messages_4 = [{"role": "user", "content": reflection_prompt}]
                        reflection_response = client.chat.completions.create(
                            model=model_choice,
                            messages=messages_4,
                            temperature=0.1
                        )
                        reflection_content = reflection_response.choices[0].message.content.strip()
                        if hasattr(reflection_response, 'usage') and reflection_response.usage:
                            _turn_tokens += getattr(reflection_response.usage, 'total_tokens', 0)
                        log_llm_interaction("Step 4: Logic Reflection", messages_4, reflection_content)

                        if "```python" in reflection_content:
                            # 觸發邏輯修正
                            status.update(label="Step 4/6: AI 發現資料為空或邏輯瑕疵，正在修正程式碼...", state="running")
                            print(">>> Logic Refinement Triggered (Empty Data or Logic Error)")
                            
                            start = reflection_content.find("```python") + len("```python\n")
                            end = reflection_content.rfind("```")
                            new_code = reflection_content[start:end].strip()
                            
                            try:
                                plt.close('all') 
                                # 重新初始化環境
                                exec_globals = {
                                    "pd": pd, 
                                    "df": df.copy(), 
                                    "st": st, 
                                    "platform": platform, 
                                    "io": io, 
                                    "plt": plt,
                                    "sns": sns 
                                }
                                f = io.StringIO()
                                with redirect_stdout(f):
                                    exec(_FONT_SETUP_CODE + "\n" + code_to_execute, exec_globals)
                                execution_output = f.getvalue()
                                
                                code_to_execute = new_code 
                                success = True 
                                
                                summary_info = {}
                                for name, val in exec_globals.items():
                                    if name.startswith('_') or name in ignore_list: continue
                                    if isinstance(val, (int, float, str, bool)):
                                        summary_info[name] = val
                                    elif isinstance(val, (pd.DataFrame, pd.Series)):
                                         summary_info[name] = f"DataFrame/Series with {len(val)} rows"
                                    elif hasattr(val, '__len__') and len(val) < 20:
                                        summary_info[name] = val
                                        
                            except Exception as logic_fix_error:
                                print(f"Logic refinement failed: {logic_fix_error}")
                                st.warning(f"⚠️ 嘗試優化圖表顯示時發生錯誤 ({logic_fix_error})，將顯示原始結果。")
                                # Fallback: 重新執行原始程式碼以恢復圖表
                                try:
                                    plt.close('all')
                                    exec_globals = {
                                        "pd": pd, "df": df.copy(), "st": st, "platform": platform, 
                                        "io": io, "plt": plt, "sns": sns
                                    }
                                    f = io.StringIO()
                                    with redirect_stdout(f):
                                        exec(_FONT_SETUP_CODE + "\n" + code_to_execute, exec_globals)
                                    execution_output = f.getvalue()
                                except:
                                    pass

                        final_figs = [plt.figure(n) for n in plt.get_fignums()]
                        if not final_figs:
                             fig_var = exec_globals.get("fig", None)
                             if fig_var:
                                 final_figs = [fig_var]

                    # --- [Step 5: 確保一定有摘要資訊] ---
                    if not summary_info:
                        summary_info = {
                            "提示": "AI 未輸出可供分析的統計變數，請根據圖表與提問邏輯生成洞察。"
                        }

                    # --- [Step 5: 顯示分析內容] ---
                    if code_to_execute:
                        # [Step 1 結果展示]
                        with st.expander("🧠 查看 AI 優化後的提問邏輯 (Step 1)", expanded=False):
                            st.markdown(f"**優化導引 (Enhanced Prompt):**\n{enhanced_prompt}")

                        with st.expander("🧾 查看 AI 生成的程式碼 (最終版)", expanded=False):
                            st.code(code_to_execute, language="python")

                    if final_figs:
                        for i, fig in enumerate(final_figs):
                            st.pyplot(fig)
                            buf = io.BytesIO()
                            fig.savefig(buf, format="png", dpi=300, bbox_inches="tight")
                            buf.seek(0)
                            st.download_button(
                                f"📥 下載圖表 {i+1}",
                                data=buf,
                                file_name=f"羽球分析_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{i}.png",
                                mime="image/png",
                                key=f"download_new_{i}"
                            )
                    elif not execution_output:
                        st.warning("⚠️ AI 沒有輸出圖表也沒有文字輸出 (可能是資料篩選後為空，建議檢查球員名稱是否正確)。")

                    # --- [Step 6: 生成數據洞察] ---
                    status.update(label="Step 5/6: 正在撰寫數據洞察...")
                    summary_text = ""
                    st.markdown("### 📊 數據洞察")
                    
                    if execution_output:
                        st.markdown("#### 📋 程式執行結果")
                        st.code(execution_output, language="text")
                        st.divider()

                    try:
                        analysis_context_str = ""
                        
                        # 加入執行輸出 (stdout) 到分析上下文
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
                        
                        insight_prompt = create_insight_prompt(enhanced_prompt, analysis_context_str)
                        
                        
                        messages_6 = [
                                {"role": "system", "content": "你是一位專業羽球教練與數據戰術大師。請針對使用者問題與核心數據結果，用教練的口吻撰寫精準的戰術洞察，提供有深度的分析，不要有統計術語，需精簡回答。"},
                                {"role": "user", "content": insight_prompt},
                            ]
                        insight = client.chat.completions.create(
                            model=model_choice,
                            messages=messages_6,
                            temperature=0.4,
                        )
                        summary_text = insight.choices[0].message.content
                        if hasattr(insight, 'usage') and insight.usage:
                            _turn_tokens += getattr(insight.usage, 'total_tokens', 0)
                        log_llm_interaction("Step 6: Insight Generation", messages_6, summary_text)
                        st.markdown(summary_text)

                    except Exception as e:
                        summary_text = f"*(無法生成洞察: {e})*"
                        st.warning(summary_text)

                    # --- [Step 7: 儲存至歷史] ---
                    code_block_for_history = f"```python\n{code_to_execute}\n```" if code_to_execute else ""
                    final_content_for_history = (
                        f"{code_block_for_history}\n\n"
                        f"---\n"
                        f"### 📊 數據洞察\n"
                        f"{summary_text}"
                    )
                    
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": final_content_for_history.strip(),
                        "figures": final_figs,
                        "enhanced_prompt": enhanced_prompt,
                        "code_to_execute": code_to_execute,
                        "turn_tokens": _turn_tokens
                    })

                    # --- Token 追蹤：寫入本輪與累積 ---
                    st.session_state.last_turn_tokens = _turn_tokens
                    st.session_state.total_tokens += _turn_tokens

                    # 即時更新頂端的儀表板 (避免要等下一次對話才更新)
                    metric_total.metric("累積消耗", f"{st.session_state.total_tokens:,}")
                    metric_last.metric("最新一輪", f"{st.session_state.last_turn_tokens:,}")

                    status.update(label=f"分析完成！(本輪 Token: {_turn_tokens:,})", state="complete")

                except Exception as e:
                    status.update(label="分析失敗", state="error")
                    st.error(f"❌ 錯誤: {e}")
                    st.session_state.messages.append({
                        "role": "assistant", "content": str(e), "figure": None
                    })

# --- 更新 ZIP 下載按鈕 (確保包含最新對話) ---
has_messages = "messages" in st.session_state and len(st.session_state.messages) > 0
if has_messages:
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_f:
        markdown_content = f"# 🏸 羽球 AI 數據分析師 - 分析報告\n"
        markdown_content += f"**儲存時間:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n---\n\n"
        chart_counter = 0
        for message in st.session_state.messages:
            role_emoji = "👤" if message["role"] == "user" else "🤖"
            role_title = "使用者提問" if message["role"] == "user" else "AI 分析師回覆"
            content_to_save = message["content"]
            markdown_content += f"### {role_emoji} {role_title}\n{content_to_save.strip()}\n\n"
            
            # --- 加入 Token 資訊 ---
            if "turn_tokens" in message:
                markdown_content += f"*(🔖 本次回答消耗 Token: {message['turn_tokens']:,})*\n\n"

            figures = message.get("figures", [])
            if not figures and message.get("figure"):
                figures = [message["figure"]]

            for fig in figures:
                chart_counter += 1
                chart_filename = f"chart_{chart_counter}.png"
                img_buffer = io.BytesIO()
                fig.savefig(img_buffer, format='png', dpi=300, bbox_inches='tight')
                img_buffer.seek(0)
                zip_f.writestr(chart_filename, img_buffer.getvalue())
                markdown_content += f"![產生的圖表 {chart_counter}]({chart_filename})\n\n"
            markdown_content += "---\n\n"
        zip_f.writestr("分析報告.md", markdown_content.encode('utf-8'))

    zip_download_placeholder.download_button(
        label="💾 下載分析報告 (ZIP)",
        data=zip_buffer.getvalue(),
        file_name=f"羽球分析報告_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
        mime="application/zip",
        key="final_zip_button"
    )