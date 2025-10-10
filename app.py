import streamlit as st
import openai
import os
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

# 設定頁面
st.set_page_config(
    page_title="羽球 AI Dashboard",
    page_icon="🏸",
    layout="wide"
)

# 初始化 LLM Client
# 切換模式：Gemini / 交大伺服器 / OpenAI 官方
API_MODE = "gemini"  # "gemini" / "nycu" / "openai"

if API_MODE == "gemini":
    client = openai.OpenAI(
        api_key=os.getenv("GEMINI_API_KEY", ""),
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
    )
elif API_MODE == "nycu":
    client = openai.OpenAI(
        api_key=os.getenv("OPENAI_API_KEY", ""),
        base_url="https://llm.nycu-adsl.cc"
    )
else:  # openai
    client = openai.OpenAI(
        api_key=os.getenv("OPENAI_API_KEY", "")
    )

# 標題
st.title("🏸 羽球個人化 Dashboard")
st.markdown("### 用自然語言查詢羽球數據")

# 側邊欄 - API 設定
with st.sidebar:
    st.header("⚙️ 設定")
    # API 模式選擇
    api_mode = st.selectbox(
        "API 模式",
        ["Gemini", "OpenAI 官方", "交大伺服器"],
        index=0
    )

    # 根據模式顯示對應的 API Key 輸入
    if api_mode == "Gemini":
        api_key_input = st.text_input(
            "Gemini API Key",
            value=os.getenv("GEMINI_API_KEY", ""),
            type="password",
            help="在 Google AI Studio 取得"
        )
        model_choice = st.selectbox(
            "選擇模型",
            ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
            index=0
        )
    else:
        api_key_input = st.text_input(
            "OpenAI API Key",
            value=os.getenv("OPENAI_API_KEY", ""),
            type="password",
            help="OpenAI API Key"
        )
        model_choice = st.selectbox(
            "選擇模型",
            ["gpt-4o-mini", "gpt-4o"],
            index=0
        )

    # 更新 client (如果 API key 有變)
    if api_key_input:
        if api_mode == "Gemini":
            client = openai.OpenAI(
                api_key=api_key_input,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
            )
        elif api_mode == "交大伺服器":
            client = openai.OpenAI(
                api_key=api_key_input,
                base_url="https://llm.nycu-adsl.cc"
            )
        else:  # OpenAI 官方
            client = openai.OpenAI(
                api_key=api_key_input
            )

    st.divider()
    st.markdown("#### 範例問題")
    st.markdown("""
    - 周天成的球種分布？
    - 殺球得分率是多少？
    - 當對手殺球時，我的下一拍回擊比例？
    - 決勝局 11 分後的得分率比較？
    """)

# 初始化對話歷史
if "messages" not in st.session_state:
    st.session_state.messages = []

# 顯示對話歷史
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 使用者輸入
if prompt := st.chat_input("請輸入你的問題..."):
    # 添加使用者訊息
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 呼叫 ChatGPT API
    with st.chat_message("assistant"):
        message_placeholder = st.empty()

        try:
            # 準備 API 請求 (使用交大伺服器)
            response = client.chat.completions.create(
                model=model_choice,
                messages=[
                    {"role": "system", "content": """你是一個羽球數據分析助手。
你需要幫助使用者分析羽球比賽數據。
可用的數據欄位包括：match_id, game_no, rally_id, stroke_no, player, opponent, shot_type, landing_zone, error_type, rally_winner 等。

當使用者提問時，你應該：
1. 理解問題的意圖
2. 說明需要哪些數據欄位
3. 建議如何計算或分析
4. 推薦適合的視覺化方式（圓餅圖/長條圖/熱區圖等）

目前是測試階段，還沒有實際數據，請先解釋如何回答這個問題。"""},
                    *st.session_state.messages
                ],
                stream=True
            )

            # 串流顯示回應
            full_response = ""
            for chunk in response:
                if chunk.choices[0].delta.content is not None:
                    full_response += chunk.choices[0].delta.content
                    message_placeholder.markdown(full_response + "▌")

            message_placeholder.markdown(full_response)

            # 添加助手回應到歷史
            st.session_state.messages.append({"role": "assistant", "content": full_response})

        except Exception as e:
            error_msg = f"❌ 錯誤：{str(e)}"
            message_placeholder.error(error_msg)
            st.session_state.messages.append({"role": "assistant", "content": error_msg})

# 清除對話按鈕
if st.sidebar.button("🗑️ 清除對話"):
    st.session_state.messages = []
    st.rerun()

# 底部資訊
st.sidebar.divider()
st.sidebar.caption("羽球 AI Dashboard v0.1")
