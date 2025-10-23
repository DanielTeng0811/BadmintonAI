import streamlit as st
import os
import io
import platform
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
import zipfile # <--- 引入必要的模組

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
    
    st.divider()

    # --- START: 全新修改的儲存對話功能 ---
    # 準備一個記憶體內的 BytesIO 物件來存放 ZIP 檔案
    zip_buffer = io.BytesIO()

    # 檢查是否有對話紀錄可以儲存
    has_messages = "messages" in st.session_state and st.session_state.messages
    
    if has_messages:
        # 使用 'with' 陳述式來安全地建立 ZIP 檔案
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_f:
            markdown_content = f"# 🏸 羽球 AI 數據分析師 - 分析報告\n"
            markdown_content += f"**儲存時間:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n---\n\n"
            
            chart_counter = 0

            for message in st.session_state.messages:
                role_emoji = "👤" if message["role"] == "user" else "🤖"
                role_title = "使用者提問" if message["role"] == "user" else "AI 分析師回覆"
                
                content_to_save = message["content"]

                # 如果是 AI 的回覆，就移除程式碼區塊
                if message["role"] == "assistant" and "```python" in content_to_save:
                    parts = content_to_save.split("```python")
                    before_code = parts[0]
                    after_code_parts = parts[1].split("```", 1)
                    after_code = after_code_parts[1] if len(after_code_parts) > 1 else ""
                    content_to_save = before_code + after_code
                
                markdown_content += f"### {role_emoji} {role_title}\n"
                markdown_content += f"{content_to_save.strip()}\n\n"
                
                # 如果訊息中有圖表，將其存入 ZIP 並在 Markdown 中引用
                if message.get("figure") is not None:
                    chart_counter += 1
                    chart_filename = f"chart_{chart_counter}.png"
                    
                    # 將圖表存入一個記憶體內的 buffer
                    img_buffer = io.BytesIO()
                    message["figure"].savefig(img_buffer, format='png', dpi=300, bbox_inches='tight')
                    img_buffer.seek(0)
                    
                    # 將圖表的 byte 寫入 ZIP 檔案
                    zip_f.writestr(chart_filename, img_buffer.getvalue())
                    
                    # 在 Markdown 內容中加入圖片的引用
                    markdown_content += f"![產生的圖表 {chart_counter}]({chart_filename})\n\n"

                markdown_content += "---\n\n"
            
            # 最後，將整理好的 Markdown 文字內容寫入 ZIP 檔案中
            zip_f.writestr("分析報告.md", markdown_content.encode('utf-8'))

    st.download_button(
       label="💾 下載分析報告 (ZIP)",
       data=zip_buffer.getvalue(),
       file_name=f"羽球分析報告_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
       mime="application/zip",
       disabled=not has_messages, # 如果沒有對話紀錄，則禁用按鈕
       help="點此可將圖文並茂的分析報告下載為 ZIP 壓縮檔"
    )
    # --- END: 全新修改的儲存對話功能 ---

    # 清除對話按鈕
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
            buf = io.BytesIO()
            message["figure"].savefig(buf, format='png', dpi=300, bbox_inches='tight')
            buf.seek(0)
            st.download_button(
                label="📥 下載圖表",
                data=buf,
                file_name=f"羽球分析_{idx}_{datetime.now().strftime('%Y%m%d')}.png",
                mime="image/png",
                key=f"download_history_{idx}",
                use_container_width=False
            )

# --- 主對話流程 ---
if prompt := st.chat_input("請輸入你的數據分析問題..."):
    if df is None:
        st.error("錯誤：無法進行分析，因為 'all_dataset.csv' 檔案不存在或無法讀取。")
    elif not api_key_input:
        st.error("請在左側側邊欄輸入您的 API Key。")
    else:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("AI 數據分析師正在思考中..."):
                try:
                    # 步驟 1: 第一次 AI 呼叫（加入對話歷史）
                    system_prompt = create_system_prompt(data_schema_info, column_definitions_info)

                    # 建立完整的對話歷史（包含 system + 所有歷史訊息）
                    conversation_messages = [{"role": "system", "content": system_prompt}]

                    # 加入所有歷史對話（但排除圖表資訊，只保留文字）
                    for msg in st.session_state.messages:
                        conversation_messages.append({
                            "role": msg["role"],
                            "content": msg["content"]
                        })

                    response = client.chat.completions.create(
                        model=model_choice,
                        messages=conversation_messages,
                    )
                    ai_response_text = response.choices[0].message.content
                    
                    code_to_execute = None
                    if "```python" in ai_response_text:
                        code_start = ai_response_text.find("```python") + len("```python\n")
                        code_end = ai_response_text.rfind("```")
                        code_to_execute = ai_response_text[code_start:code_end].strip()

                    # 步驟 2: 執行程式碼
                    final_fig = None
                    summary_data = None
                    if code_to_execute:
                        exec_globals = {
                            "pd": pd, "st": st, "df": df.copy(),
                            "platform": platform, "io": io
                        }
                        exec(code_to_execute, exec_globals)
                        final_fig = exec_globals.get('fig', None)
                        
                        for var_name, var_value in exec_globals.items():
                            if isinstance(var_value, (pd.DataFrame, pd.Series)) and var_name != 'df':
                                summary_data = var_value
                                break
                    
                    # 步驟 3: 第二次 AI 呼叫 (生成洞察)
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
                                # 不要加入對話歷史，只專注於當前的表格分析
                                insight_response = client.chat.completions.create(
                                    model=model_choice,
                                    messages=[
                                        {"role": "system", "content": "你是一位專業的數據分析師，專門從數據表格中解讀出有價值的洞察。請只分析提供的表格數據，用繁體中文簡潔說明重點。"},
                                        {"role": "user", "content": insight_prompt}
                                    ],
                                    temperature=0.3,  # 降低溫度，讓回答更一致
                                )
                                summary_text = insight_response.choices[0].message.content
                            except Exception as e:
                                summary_text = f"\n\n*(無法自動生成數據洞察: {e})*"

                    # 步驟 4: 整合結果並顯示
                    final_content = ai_response_text
                    if summary_text:
                        final_content += f"\n\n---\n#### 📊 數據洞察\n{summary_text}"
                    
                    st.markdown(final_content)
                    if code_to_execute:
                        with st.expander("點此查看 AI 生成的 Python 程式碼"):
                            st.code(code_to_execute, language="python")

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

                    # 步驟 5: 存入 session state
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": final_content,
                        "figure": final_fig
                    })

                except Exception as e:
                    st.error(f"處理您的請求時發生錯誤：{e}")
                    st.session_state.messages.append({"role": "assistant", "content": str(e), "figure": None})