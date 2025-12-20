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
from config.prompts import create_system_prompt
from utils.data_loader import load_all_data
from utils.ai_client import initialize_client

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

    if api_mode == "Gemini":
        model_choice = st.selectbox("選擇模型",["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"], index=0)
    else:
        model_choice = st.selectbox("選擇模型", ["gpt-4o-mini", "gpt-4o"], index=1)

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

    # --- ZIP 匯出功能 ---
    zip_buffer = io.BytesIO()
    has_messages = "messages" in st.session_state and st.session_state.messages
    if has_messages:
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_f:
            markdown_content = f"# 🏸 羽球 AI 數據分析師 - 分析報告\n"
            markdown_content += f"**儲存時間:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n---\n\n"
            chart_counter = 0
            for message in st.session_state.messages:
                role_emoji = "👤" if message["role"] == "user" else "🤖"
                role_title = "使用者提問" if message["role"] == "user" else "AI 分析師回覆"
                content_to_save = message["content"]
                
                # 在儲存時，將程式碼區塊保留
                markdown_content += f"### {role_emoji} {role_title}\n{content_to_save.strip()}\n\n"
                
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

    st.download_button(
        label="💾 下載分析報告 (ZIP)",
        data=zip_buffer.getvalue(),
        file_name=f"羽球分析報告_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
        mime="application/zip",
        disabled=not has_messages
    )

    if st.button("🗑️ 清除對話"):
        st.session_state.messages = []
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
    # Clear debug log
    with open("llm_debug_log.txt", "w", encoding="utf-8") as f:
        pass

    if df is None:
        st.error("❌ 找不到 'all_dataset.csv'。")
    elif not api_key_input:
        st.error("⚠️ 請輸入 API Key。")
    else:
        # 顯示使用者輸入
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # AI 回覆與執行
        with st.chat_message("assistant"):
            with st.status("AI 正在分析並生成圖表...", expanded=True) as status:
                try:
                    # 1. 準備 Prompt
                    system_prompt = create_system_prompt(data_schema_info, column_definitions_info, court_place_info)
                    
                    # 簡單的歷史對話 Context (若有開啟)
                    messages = [{"role": "system", "content": system_prompt}]
                    if use_history:
                        # 簡單取最近 4 筆對話
                        recent = st.session_state.messages[-5:-1] if len(st.session_state.messages) > 1 else []
                        for msg in recent:
                            if msg["role"] in ["user", "assistant"] and "content" in msg:
                                messages.append({"role": msg["role"], "content": msg["content"]})
                    
                    messages.append({"role": "user", "content": prompt})

                    # 2. 呼叫 LLM (Single Call)
                    status.write("正在撰寫程式碼...")
                    response = client.chat.completions.create(
                        model=model_choice,
                        messages=messages,
                        temperature=0.1 # 降低隨機性確保程式碼穩定
                    )
                    ai_response = response.choices[0].message.content
                    log_llm_interaction("Single Step Analysis", messages, ai_response)

                    # 3. 提取程式碼
                    code_to_execute = None
                    if "```python" in ai_response:
                        start = ai_response.find("```python") + len("```python\n")
                        end = ai_response.rfind("```")
                        code_to_execute = ai_response[start:end].strip()
                    elif "```" in ai_response: # 容錯
                         start = ai_response.find("```") + 3
                         end = ai_response.rfind("```")
                         code_to_execute = ai_response[start:end].strip()
                    
                    if not code_to_execute:
                         st.error("AI 未生成程式碼，請重試。")
                         st.markdown(ai_response) # 顯示原始回應
                    else:
                        status.write("正在執行程式碼...")
                        
                        # 4. 執行程式碼
                        # 清除舊圖
                        plt.close('all')
                        
                        exec_globals = {
                            "pd": pd, "df": df.copy(), "st": st, "platform": platform, 
                            "io": io, "plt": plt, "sns": sns
                        }
                        
                        f = io.StringIO()
                        with redirect_stdout(f):
                            try:
                                exec(code_to_execute, exec_globals)
                            except Exception as e:
                                st.error(f"程式執行錯誤: {e}")
                                print(f"Execution Error: {e}")
                                # 這裡不再自動修復，因為要求只能呼叫一次 LLM
                                # 但可以顯示錯誤碼供參考
                                st.code(code_to_execute, language="python")
                                raise e # 中斷

                        execution_output = f.getvalue()
                        
                        # 5. 顯示結果
                        # 顯示圖表
                        final_figs = [plt.figure(n) for n in plt.get_fignums()]
                        if not final_figs and "fig" in exec_globals:
                             if exec_globals["fig"]:
                                 final_figs = [exec_globals["fig"]]

                        if final_figs:
                            for i, fig in enumerate(final_figs):
                                st.pyplot(fig)
                                # 下載按鈕
                                buf = io.BytesIO()
                                fig.savefig(buf, format="png", dpi=300, bbox_inches="tight")
                                buf.seek(0)
                                st.download_button(
                                    f"📥 下載圖表 {i+1}",
                                    data=buf,
                                    file_name=f"analysis_{datetime.now().strftime('%H%M%S')}_{i}.png",
                                    mime="image/png",
                                    key=f"dl_{datetime.now().timestamp()}_{i}"
                                )
                        else:
                            if execution_output:
                                st.info("執行完成，無圖表產出。")
                            else:
                                st.warning("執行完成，但無圖表也無輸出。")

                        # 顯示文字輸出
                        if execution_output:
                            with st.expander("查看執行輸出 (Stdout)", expanded=True):
                                st.text(execution_output)

                        # 顯示程式碼 (Optional)
                        with st.expander("查看生成程式碼", expanded=False):
                            st.code(code_to_execute, language="python")

                        # 儲存歷史
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": f"分析完成。\n\n{ai_response if not final_figs else ''}", # 若有圖就不重複顯示大量文字
                            "figures": final_figs
                        })

                        status.update(label="分析完成", state="complete")

                except Exception as e:
                    status.update(label="發生錯誤", state="error")
                    st.error(f"處理失敗: {e}")
