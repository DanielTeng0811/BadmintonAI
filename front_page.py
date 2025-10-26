import streamlit as st
import os
import io
import platform
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
import zipfile

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

# --- Streamlit UI ---
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
                
                if message.get("figure") is not None:
                    chart_counter += 1
                    chart_filename = f"chart_{chart_counter}.png"
                    img_buffer = io.BytesIO()
                    message["figure"].savefig(img_buffer, format='png', dpi=300, bbox_inches='tight')
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

# 顯示歷史
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
            )

# --- 主對話流程 ---
if prompt := st.chat_input("請輸入你的數據分析問題..."):
    if df is None:
        st.error("❌ 找不到 'all_dataset.csv'。")
    elif not api_key_input:
        st.error("⚠️ 請輸入 API Key。")
    else:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("AI 數據分析師正在思考中..."):
                try:
                    # Step 1️⃣: 生成分析程式碼
                    system_prompt = create_system_prompt(data_schema_info, column_definitions_info)
                    conversation = [{"role": "system", "content": system_prompt}]
                    for m in st.session_state.messages:
                        conversation.append({"role": m["role"], "content": m["content"]})

                    response = client.chat.completions.create(
                        model=model_choice, messages=conversation
                    )
                    ai_response = response.choices[0].message.content

                    # 取出 Python code
                    code_to_execute = None
                    if "```python" in ai_response:
                        start = ai_response.find("```python") + len("```python\n")
                        end = ai_response.rfind("```")
                        code_to_execute = ai_response[start:end].strip()

                    # Step 2️⃣: 執行程式 (核心修改處 1)
                    final_fig = None
                    summary_info = {} # 改用字典來儲存所有小型變數
                    if code_to_execute:
                        exec_globals = {"pd": pd, "df": df.copy(), "st": st, "platform": platform, "io": io}
                        exec(code_to_execute, exec_globals)
                        final_fig = exec_globals.get("fig", None)
                        
                        # --- 修改開始 ---
                        # 遍歷所有執行後產生的變數，收集小型、重要的資訊
                        ignore_list = ['df', 'pd', 'st', 'platform', 'io', 'fig', 'np', 'plt', 'sns']
                        for name, val in exec_globals.items():
                            # 忽略內建變數和要排除的變數
                            if name.startswith('_') or name in ignore_list:
                                continue

                            # 條件1: 抓取所有基本型別的變數 (數字, 字串, 布林)
                            if isinstance(val, (int, float, str, bool)):
                                summary_info[name] = val
                            # 條件2: 抓取長度 < 20 的 list, tuple, dict, Series, DataFrame
                            elif hasattr(val, '__len__') and not isinstance(val, str) and len(val) < 20:
                                summary_info[name] = val
                        # --- 修改結束 ---


                    # Step 3️⃣: 確保一定有摘要資訊 (核心修改處 2)
                    if not summary_info: # 改為檢查字典是否為空
                        summary_info = {
                            "提示": "AI 未輸出可供分析的統計變數，請根據圖表與提問邏輯生成洞察。"
                        }

                    # Step 4️⃣: 顯示分析內容
                    if code_to_execute:
                        with st.expander("🧾 查看 AI 生成的程式碼", expanded=False):
                            st.code(code_to_execute, language="python")

                    if final_fig:
                        st.pyplot(final_fig)
                        buf = io.BytesIO()
                        final_fig.savefig(buf, format="png", dpi=300, bbox_inches="tight")
                        buf.seek(0)
                        st.download_button(
                            "📥 下載圖表",
                            data=buf,
                            file_name=f"羽球分析_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png",
                            mime="image/png",
                        )
                    else:
                        st.warning("⚠️ AI 沒有輸出圖表。")

                    # Step 5️⃣: 一定生成數據洞察 (核心修改處 3)
                    summary_text = ""
                    st.markdown("### 📊 數據洞察")
                    with st.spinner("AI 正在撰寫洞察..."):
                        try:
                            # --- 修改開始 ---
                            # 將 summary_info 字典格式化為給 AI 的 prompt 字串
                            analysis_context_str = ""
                            if not summary_info:
                                analysis_context_str = "AI 程式碼未產生任何可供分析的摘要變數。"
                            else:
                                analysis_context_str += "程式碼執行後，擷取出以下核心變數與其值：\n\n"
                                for name, val in summary_info.items():
                                    analysis_context_str += f"### 變數 `{name}` (型別: `{type(val).__name__}`)\n"
                                    
                                    # 對 DataFrame 和 Series 特別使用 markdown 格式化
                                    if isinstance(val, (pd.DataFrame, pd.Series)):
                                        analysis_context_str += f"```markdown\n{val.to_markdown()}\n```\n\n"
                                    else:
                                        analysis_context_str += f"```\n{str(val)}\n```\n\n"
                            with open("analysis_context_output.txt", "w", encoding="utf-8") as f:
                                f.write(analysis_context_str)
                            # 建立新的 insight prompt
                            insight_prompt = f"""
                            你是一位專業的羽球數據分析師。
                            使用者的原始問題是：「{prompt}」
                            
                            根據這個問題，AI 產生並執行了一段 Python 程式碼，程式碼執行後產生的核心數據變數如下。

                            --- 核心數據變數 ---
                            {analysis_context_str}
                            --- 核心數據變數結束 ---

                            請你基於「使用者問題」和上述所有「核心數據變數」，用繁體中文撰寫一份精簡、條理分明的數據洞察報告。
                            報告應包含以下部分：
                            1.  **直接回答**：直接且明確地回答使用者的問題。
                            2.  **關鍵發現**：從數據中提煉出 1 到 3 個最關鍵的觀察或趨勢，並說明是根據哪些變數得出的結論。
                            3.  **總結**：用一句話總結分析結果。

                            請避免重複描述數據內容，專注於提供有價值的見解。
                            """
                            # --- 修改結束 ---
                            
                            insight = client.chat.completions.create(
                                model=model_choice,
                                messages=[
                                    {"role": "system", "content": "你是一位專業羽球數據分析師，請針對使用者問題與核心數據結果，撰寫精準洞察。"},
                                    {"role": "user", "content": insight_prompt},
                                ],
                                temperature=0.4,
                            )
                            summary_text = insight.choices[0].message.content
                            st.markdown(summary_text)

                        except Exception as e:
                            summary_text = f"*(無法生成洞察: {e})*"
                            st.warning(summary_text)

                    # Step 6️⃣: 儲存至歷史
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
                        "figure": final_fig,
                    })

                except Exception as e:
                    st.error(f"❌ 錯誤: {e}")
                    st.session_state.messages.append({
                        "role": "assistant", "content": str(e), "figure": None
                    })