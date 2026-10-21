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
from utils.paths import (
    COURT_PLACE_FILE,
    LLM_DEBUG_LOG,
    PROCESSED_CSV,
    ensure_runtime_dirs,
)
from utils.analysis_workflow import (
    extract_conversation_context,
    run_clarification_check,
    run_prompt_enhancement,
    run_code_generation,
    run_code_execution,
    run_code_execution_loop,
    run_logic_reflection,
    run_insight_generation
)


# --- 初始設定與環境變數載入 ---
load_dotenv()
ensure_runtime_dirs()

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
        with open(COURT_PLACE_FILE, "r", encoding="utf-8") as f:
            return f.read()
    except:
        return ""

court_place_info = load_court_info()


# --- 🔒 通關密碼保護 (Simple Auth) ---
# 這是為了讓 App 可公開網址 (方便分享)，但只讓知道密碼的人使用 (保護 API Key)
def check_password():
    """Returns `True` if the user had the correct password."""

    # 1. 如果已經驗證過，直接回傳 True
    if st.session_state.get("password_correct", False):
        return True

    # 2. 不提供預設密碼，避免公開部署時意外使用已知憑證。
    correct_password = get_api_key("APP_PASSWORD")
    if not correct_password:
        st.error("⚠️ 服務尚未設定 APP_PASSWORD。請在 .env 或部署平台的 Secrets 中設定後再啟動。")
        return False

    # 3. 顯示輸入框
    st.header("🔒 請輸入通關密碼")
    st.write("此應用程式受密碼保護，以避免 API Key 被濫用。")
    password_input = st.text_input("密碼", type="password")

    if st.button("登入"):
        if password_input == correct_password:
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
    api_mode = st.selectbox("API 模式", ["Gemini", "OpenAI 官方", "交大伺服器", "Claude"], index=1)
    _env_var_map = {"Gemini": "GEMINI_API_KEY", "Claude": "ANTHROPIC_API_KEY"}
    api_key_env_var = _env_var_map.get(api_mode, "OPENAI_API_KEY")

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
    st.caption("部署在 Hugging Face Spaces 時，上傳資料只會暫存於目前的容器；重新啟動後請重新上傳。")
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
    elif api_mode == "Claude":
        model_choice = st.selectbox("選擇模型", ["claude-sonnet-4-6", "claude-3-opus-20240229"], index=0)
    else:
        model_choice = st.selectbox("選擇模型", ["gpt-4o-mini", "gpt-4o"], index=1)

    st.divider()

    st.header("⚡ 流程控制")
    skip_logic_reflection = st.checkbox("略過邏輯檢查 (加速)", value=False, help="打勾後將跳過 AI 自我審查與修復步驟，以換取更快的生成速度。")

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
    with open(LLM_DEBUG_LOG, "w", encoding="utf-8") as f:
        pass # Truncate file to 0 bytes

    if df is None:
        st.error(f"❌ 找不到處理後資料檔：{PROCESSED_CSV}")
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
                        # 取得 Prompt
                        clarification_prompt = create_clarification_check_prompt(prompt, data_schema_info)
                        # 執行工作流
                        clarification_data = run_clarification_check(client, model_choice, clarification_prompt)

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

                    # --- Token 計數器：本輪累加 ---
                    _turn_tokens = 0

                    # --- [Step 1: 轉化使用者問題] ---
                    status.update(label="Step 1/6: 正在釐清您的問題...")
                    
                    # 提前準備兩種歷史對話 (供 Step 1 與 Step 2 分別使用)
                    step1_history, step2_history_candidate = extract_conversation_context(
                        st.session_state.messages, use_history
                    )

                    enhancement_system_prompt = create_enhancement_system_prompt()
                    enhancement_result = run_prompt_enhancement(client, model_choice, enhancement_system_prompt, prompt, step1_history)
                    
                    enhanced_prompt = enhancement_result["enhanced_prompt"]
                    needs_court_info = enhancement_result["needs_court_info"]
                    is_related_to_previous_code = enhancement_result["is_related"]
                    required_column_groups = enhancement_result.get("required_column_groups", [])
                    _turn_tokens += enhancement_result["tokens"]

                    # --- [Step 2: 生成分析程式碼] ---
                    status.update(label="Step 2/6: 正在生成分析程式碼...")
                    from utils.data_loader import filter_schema_and_definitions
                    filtered_schema, filtered_defs = filter_schema_and_definitions(
                        required_column_groups, 
                        data_schema_info, 
                        column_definitions_info
                    )
                    system_prompt = create_system_prompt(
                        filtered_schema, 
                        filtered_defs, 
                        court_place_info if needs_court_info else None
                    )
                    
                    history_for_step2 = step2_history_candidate if is_related_to_previous_code else []
                    gen_result = run_code_generation(client, model_choice, system_prompt, enhanced_prompt, history_for_step2)
                    
                    code_to_execute = gen_result["code"]
                    _turn_tokens += gen_result["tokens"]

                    # --- [Step 3: 執行程式 (Runtime Error Fix Loop)] ---
                    status.update(label="Step 3/6: 正在執行程式碼...")
                    
                    final_figs = []
                    summary_info = {}
                    execution_output = ""
                    
                    if code_to_execute:
                        # 定義 UI 更新回調
                        def execution_status_callback(msg):
                            status.update(label=msg, state="running")

                        loop_result = run_code_execution_loop(
                            client, model_choice, code_to_execute, df, 
                            system_prompt, enhanced_prompt, 
                            max_retries=3, 
                            status_callback=execution_status_callback,
                            extended_globals={"st": st}
                        )
                        
                        code_to_execute = loop_result["final_code"]
                        _turn_tokens += loop_result["tokens"]
                        
                        exec_result = loop_result["exec_result"]
                        execution_output = exec_result["stdout"]
                        summary_info = exec_result["summary_info"]
                        final_figs = exec_result["figs"]
                        
                        if not loop_result["success"]:
                            st.error(f"❌ 無法修復程式碼執行錯誤。\n{exec_result['error']}")

                        # --- [Step 4: 邏輯反饋與修正 (Logic Reflection Loop)] ---
                        if skip_logic_reflection:
                            st.info("⚡ 已選擇略過邏輯審查", icon="⚡")
                            status.update(label="⚡ 略過邏輯審查", state="running")
                        else:
                            status.update(label="Step 4/6: AI 正在檢查分析結果的邏輯性...")
                            
                            reflection_prompt = create_reflection_prompt(enhanced_prompt, code_to_execute, execution_output, summary_info)
                            reflection_result = run_logic_reflection(client, model_choice, reflection_prompt)
                            _turn_tokens += reflection_result["tokens"]

                            if reflection_result["new_code"]:
                                status.update(label="Step 4/6: AI 發現邏輯瑕疵，正在修正程式碼...")
                                old_code = code_to_execute
                                code_to_execute = reflection_result["new_code"]
                                # 重新執行修正後的代碼
                                exec_result = run_code_execution(code_to_execute, df, extended_globals={"st": st})
                                if exec_result["success"]:
                                    summary_info = exec_result["summary_info"]
                                    final_figs = exec_result["figs"]
                                    execution_output = exec_result["stdout"]
                                else:
                                    st.warning(f"⚠️ 嘗試優化圖表顯示時發生錯誤 ({exec_result['error']})，將顯示原始結果。")
                                    code_to_execute = old_code # 回滾到修改前的代碼

                    # --- [Step 5: 顯示結果] ---
                    if code_to_execute:
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
                    st.markdown("### 📊 數據洞察")
                    
                    if execution_output:
                        st.markdown("#### 📋 程式執行結果")
                        st.code(execution_output, language="text")
                        st.divider()

                    try:
                        insight_system_prompt = "你是一位專業的羽球數據分析師與教練，請根據使用者的提問與程式執行結果，提供精煉且具戰術意義的洞察。"
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
                        
                        insight_result = run_insight_generation(client, model_choice, insight_system_prompt, insight_prompt)
                        summary_text = insight_result["insight"]
                        _turn_tokens += insight_result["tokens"]
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
