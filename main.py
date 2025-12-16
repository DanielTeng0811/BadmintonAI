import streamlit as st
import io
from dotenv import load_dotenv
from datetime import datetime

# 自訂模組
from utils.data_loader import load_all_data
from utils.ai_client import initialize_client
from components.sidebar import render_sidebar
from logic.analysis_flow import process_user_query

# --- 初始設定與環境變數載入 ---
load_dotenv()

# 設定頁面 (必須是第一個 st 指令)
st.set_page_config(
    page_title="羽球 AI 數據分析師",
    page_icon="🏸",
    layout="wide"
)

# --- 資料載入 ---
df, data_schema_info, column_definitions_info = load_all_data()

# --- Streamlit UI ---
st.title("🏸 羽球 AI 數據分析師")
st.markdown("#### 透過自然語言，直接生成數據分析圖表")

# --- 渲染側邊欄 ---
settings = render_sidebar()
# 解包設定
api_mode = settings.get("api_mode", "OpenAI 官方")
api_key_input = settings.get("api_key_input", "")
model_choice = settings.get("model_choice", "gpt-4o")
enable_clarification = settings.get("enable_clarification", False)

# 初始化 client
client = initialize_client(api_mode, api_key_input)

# --- 初始化 Session State ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "awaiting_clarification" not in st.session_state:
    st.session_state.awaiting_clarification = False
if "clarification_data" not in st.session_state:
    st.session_state.clarification_data = None
if "original_prompt" not in st.session_state:
    st.session_state.original_prompt = ""

# --- 顯示歷史對話 ---
for idx, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        # 若有優化後的提問邏輯，顯示在對話中
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
use_history = st.toggle("🔗 接續前文 (Track History)", value=False, help="開啟後，AI 將參考最近的對話紀錄來回答問題。")

if prompt := st.chat_input("請輸入你的數據分析問題..."):
    # Clear debug log on new input
    with open("llm_debug_log.txt", "w", encoding="utf-8") as f:
        pass 

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
            # 這裡我們不設定 skip_clarification 變數給 analysis_flow (因為它內部沒有參數接收)
            # 但我們可以透過 prompt 內容 (包含 "補充說明") 讓 analysis_flow 內部的判斷機制跳過檢查
            # (在 analysis_flow.py Line 45 `if "補充說明:" in prompt: skip_clarification_check = True`)
        else:
            # 儲存問題與追蹤狀態
            st.session_state.messages.append({
                "role": "user", 
                "content": prompt,
                "tracked": use_history 
            })

        # 呼叫邏輯處理核心
        process_user_query(
            prompt=prompt,
            client=client,
            model_choice=model_choice,
            df=df,
            data_schema_info=data_schema_info,
            enable_clarification=enable_clarification,
            use_history=use_history
        )
