import streamlit as st
import os
import io
import platform
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

# 自訂模組
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

# --- 資料載入 ---
df, data_schema_info, column_definitions_info = load_all_data()


# --- Streamlit UI 介面 ---
st.title("🏸 羽球 AI 數據分析師")
st.markdown("#### 透過自然語言，直接生成數據分析圖表")

# 側邊欄
with st.sidebar:
    st.header("⚙️ API 設定")
    api_mode = st.selectbox("API 模式", ["Gemini", "OpenAI 官方", "交大伺服器"], index=0)

    api_key_env_var = "GEMINI_API_KEY" if api_mode == "Gemini" else "OPENAI_API_KEY"
    api_key_input = st.text_input(
        f"{api_mode} API Key",
        value=os.getenv(api_key_env_var, ""),
        type="password"
    )

    if api_mode == "Gemini":
        model_choice = st.selectbox("選擇模型", ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"], index=0)
    else:
        model_choice = st.selectbox("選擇模型", ["gpt-4o-mini", "gpt-4o"], index=0)

    st.divider()
    st.markdown("#### 範例問題")
    st.info("""
    - 球員 A 的各球種分佈是怎麼樣的？請用圓餅圖呈現。
    - 哪個落點 (`landing_zone`) 的球最常出現？請用長條圖表示。
    - 各球員 (`player`) 的殺球 (`smash`) 次數比較。
    - 誰是失誤王？請統計各球員的失誤次數。
    """)

# 初始化 AI client
client = initialize_client(api_mode, api_key_input)

# 初始化對話歷史
if "messages" not in st.session_state:
    st.session_state.messages = []

# 顯示對話歷史
for idx, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if "figure" in message and message["figure"] is not None:
            st.pyplot(message["figure"])

            # 為歷史圖表也加入下載按鈕
            buf = io.BytesIO()
            message["figure"].savefig(buf, format='png', dpi=300, bbox_inches='tight')
            buf.seek(0)

            st.download_button(
                label="📥 下載圖表",
                data=buf,
                file_name=f"羽球分析_{idx}_{datetime.now().strftime('%Y%m%d')}.png",
                mime="image/png",
                key=f"download_history_{idx}",  # 每個按鈕需要唯一的 key
                use_container_width=False
            )


# --- 主對話流程 ---
if prompt := st.chat_input("請輸入你的數據分析問題..."):
    if df is None:
        st.error("錯誤：無法進行分析，因為 'all_dataset.csv' 檔案不存在或無法讀取。")
    elif not api_key_input:
        st.error("請在左側側邊欄輸入您的 API Key。")
    else:
        # 將使用者問題加入歷史紀錄並顯示
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # 準備呼叫 API
        with st.chat_message("assistant"):
            with st.spinner("AI 數據分析師正在生成程式碼並繪製圖表中..."):
                try:
                    system_prompt = create_system_prompt(data_schema_info, column_definitions_info)
                    
                    response = client.chat.completions.create(
                        model=model_choice,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt}
                        ],
                    )
                    
                    ai_response_text = response.choices[0].message.content
                    
                    # 從 AI 回應中解析程式碼
                    code_to_execute = None
                    if "```python" in ai_response_text:
                        code_start = ai_response_text.find("```python") + len("```python\n")
                        code_end = ai_response_text.rfind("```")
                        code_to_execute = ai_response_text[code_start:code_end].strip()

                    # 顯示 AI 的文字說明
                    st.markdown(ai_response_text)
                    
                    final_fig = None
                    if code_to_execute:
                        # 顯示即將執行的程式碼
                        with st.expander("點此查看 AI 生成的 Python 程式碼"):
                            st.code(code_to_execute, language="python")
                        
                        # 建立一個安全的執行環境
                        import platform
                        exec_globals = {
                            "pd": pd,
                            "st": st,
                            "df": df.copy(),  # 使用副本以防意外修改
                            "platform": platform  # 讓 AI 生成的程式碼能判斷作業系統
                        }
                        
                        # 執行程式碼
                        exec(code_to_execute, exec_globals)
                        
                        # 從執行環境中獲取圖表物件
                        if 'fig' in exec_globals:
                            final_fig = exec_globals['fig']
                            st.pyplot(final_fig)

                            # 加入下載圖表按鈕
                            buf = io.BytesIO()
                            final_fig.savefig(buf, format='png', dpi=300, bbox_inches='tight')
                            buf.seek(0)

                            st.download_button(
                                label="📥 下載圖表",
                                data=buf,
                                file_name=f"羽球分析_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png",
                                mime="image/png",
                                use_container_width=False
                            )
                        else:
                            st.warning("AI 生成的程式碼中未找到名為 `fig` 的圖表物件。")

                    # 將完整結果存入 session state
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": ai_response_text,
                        "figure": final_fig
                    })

                except Exception as e:
                    st.error(f"發生錯誤：{e}")
                    st.session_state.messages.append({"role": "assistant", "content": str(e), "figure": None})

# 清除對話按鈕
if st.sidebar.button("🗑️ 清除對話"):
    st.session_state.messages = []
    st.rerun()
