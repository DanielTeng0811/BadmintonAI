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
        # 保持與您原始碼一致的模型選項
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
    
    # 新增清除對話按鈕
    if st.button("🗑️ 清除對話"):
        st.session_state.messages = []
        st.rerun()

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
            with st.spinner("AI 數據分析師正在思考中..."):
                try:
                    # --- 步驟 1: 第一次 AI 呼叫，生成程式碼和初步說明 ---
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

                    # --- 步驟 2: 如果有程式碼，就執行並準備好圖表和摘要數據 ---
                    final_fig = None
                    summary_data = None
                    if code_to_execute:
                        exec_globals = {
                            "pd": pd, "st": st, "df": df.copy(),
                            "platform": platform, "io": io
                        }
                        # 執行程式碼
                        exec(code_to_execute, exec_globals)
                        
                        # 獲取圖表物件
                        final_fig = exec_globals.get('fig', None)
                        
                        # 尋找摘要數據 (DataFrame or Series)
                        for var_name, var_value in exec_globals.items():
                            if isinstance(var_value, (pd.DataFrame, pd.Series)) and var_name != 'df':
                                summary_data = var_value
                                break
                    
                    # --- 步驟 3: 如果有摘要數據，進行第二次 AI 呼叫以生成數據洞察 ---
                    summary_text = ""
                    if summary_data is not None:
                        with st.spinner("AI 正在分析數據並生成文字洞察..."):
                            try:
                                table_markdown = summary_data.to_markdown()
                                insight_prompt = f"""
                                這是原始的使用者問題: "{prompt}"
                                這是根據問題計算出的摘要表格:
                                ```markdown
                                {table_markdown}
                                ```
                                請扮演專業數據分析師，根據此表格，用繁體中文撰寫一段簡短精闢的數據洞察。
                                直接提供結論，不要複述問題或程式碼。
                                """
                                insight_response = client.chat.completions.create(
                                    model=model_choice,
                                    messages=[
                                        {"role": "system", "content": "你是一位專業的數據分析師，專門從數據表格中解讀出有價值的洞察。"},
                                        {"role": "user", "content": insight_prompt}
                                    ],
                                    temperature=0.5,
                                )
                                summary_text = insight_response.choices[0].message.content
                            except Exception as e:
                                # 如果生成洞察失敗，給一個提示訊息，但不中斷整個流程
                                summary_text = f"\n\n*(無法自動生成數據洞察: {e})*"

                    # --- 步驟 4: 整合所有結果並一次性顯示 ---
                    
                    # 組合最終的文字輸出
                    final_content = ai_response_text
                    if summary_text:
                        final_content += f"\n\n---\n#### 📊 數據洞察\n{summary_text}"
                    
                    # 顯示文字和程式碼區塊
                    st.markdown(final_content)
                    if code_to_execute:
                        with st.expander("點此查看 AI 生成的 Python 程式碼"):
                            st.code(code_to_execute, language="python")

                    # 顯示圖表和下載按鈕
                    if final_fig:
                        st.pyplot(final_fig)
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
                    elif code_to_execute and not final_fig:
                         st.warning("AI 生成的程式碼已執行，但未找到名為 `fig` 的圖表物件。")

                    # --- 步驟 5: 將完整結果存入 session state ---
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": final_content,
                        "figure": final_fig
                    })

                except Exception as e:
                    st.error(f"處理您的請求時發生錯誤：{e}")
                    st.session_state.messages.append({"role": "assistant", "content": str(e), "figure": None})