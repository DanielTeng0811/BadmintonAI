import streamlit as st
import os
import io
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
            # 使用 st.status 來顯示多步驟進程
            with st.status("AI 數據分析師正在處理中...") as status:
                try:
                    # --- [Step 0: 轉化使用者問題] ---
                    status.update(label="Step 1/5: 正在釐清您的問題...")
                    
                    enhancement_system_prompt = f"""
                    你是一個輔助系統，你的任務是將使用者的簡短數據分析問題，轉化為一個更清晰、更完整、更具體的數據分析任務描述，必須考慮使用者所有方面的可能，及數據中所有欄位的關聯性。
                    這個描述將被交給另一個 AI (Python 程式碼生成器) 來執行。
                    
                    你必須考慮以下的資料庫 schema：
                    {data_schema_info}
                    
                    你的輸出**只能**包含轉化後的繁體中文問題敘述，不要有任何前言、後語或解釋。
                    """
                    
                    enhancement_response = client.chat.completions.create(
                        model=model_choice,
                        messages=[
                            {"role": "system", "content": enhancement_system_prompt},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.2
                    )
                    enhanced_prompt = enhancement_response.choices[0].message.content.strip()
                    print(f"Enhanced Prompt: {enhanced_prompt}")

                    # --- [Step 1: 生成分析程式碼] ---
                    status.update(label="Step 2/5: 正在生成分析程式碼...")
                    system_prompt = create_system_prompt(data_schema_info, column_definitions_info)
                    
                    # [修改點]：注入通用且穩健的視覺化指導原則，而非強制特定方法
                    system_prompt += """
                    \n**數據分析與視覺化最佳實踐 (Analysis & Visualization Best Practices):**
                    1. **資料型態意識 (Data Type Awareness)**:
                       - 在彙整或繪圖前，請確認欄位是「連續數值 (Float)」還是「離散類別 (Category/Int)」。
                       - 若是對「連續座標 (Float)」進行分析 (如落點、跑動位置)，**嚴禁**直接使用 `groupby` 計算次數，因為座標幾乎不會完全重複，這會導致圖表空白或座標軸崩潰。
                    2. **座標軸可讀性 (Label Readability)**:
                       - 避免將大量浮點數直接作為軸標籤。
                    3. **資料量檢查 (Data Integrity)**:
                       - 在繪圖前，務必檢查篩選後的 DataFrame 是否為空 (`if len(filtered_df) > 0: ...`)。
                    """

                    conversation = [{"role": "system", "content": system_prompt}]
                    if len(st.session_state.messages) > 1:
                        for m in st.session_state.messages[:-1]:
                            if m.get("content"):
                                conversation.append({"role": m["role"], "content": m["content"]})
                    
                    conversation.append({"role": "user", "content": enhanced_prompt})

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

                    # --- [Step 2: 執行程式 (Runtime Error Fix Loop)] ---
                    status.update(label="Step 3/5: 正在執行程式碼...")
                    
                    final_fig = None
                    summary_info = {}
                    exec_globals = {} # 初始化環境變數
                    
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
                                exec(code_to_execute, exec_globals)
                                success = True
                                break 
                            except Exception as e:
                                retry_count += 1
                                last_error = e
                                status.update(label=f"Step 3/5: 程式執行錯誤，AI 正在修復語法 (嘗試 {retry_count}/{max_retries})...", state="running")
                                
                                conversation.append({"role": "assistant", "content": f"```python\n{code_to_execute}\n```"})
                                error_feedback = f"執行上述程式碼時發生錯誤: {str(e)}。請修正錯誤並重新輸出完整程式碼 (包含必要的 import)。"
                                conversation.append({"role": "user", "content": error_feedback})
                                
                                correction_response = client.chat.completions.create(model=model_choice, messages=conversation)
                                ai_correction = correction_response.choices[0].message.content
                                
                                if "```python" in ai_correction:
                                    start = ai_correction.find("```python") + len("```python\n")
                                    end = ai_correction.rfind("```")
                                    code_to_execute = ai_correction[start:end].strip() # 更新代碼

                        if not success:
                            raise last_error

                        # --- 提取變數 (供下一步邏輯檢查使用) ---
                        ignore_list = ['df', 'pd', 'st', 'platform', 'io', 'fig', 'np', 'plt', 'sns']
                        for name, val in exec_globals.items():
                            if name.startswith('_') or name in ignore_list: continue
                            
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

                        # --- [Step 2.5: 邏輯反饋與修正 (Logic Reflection Loop)] ---
                        status.update(label="Step 4/5: AI 正在檢查分析結果的邏輯性...")
                        
                        reflection_context = ""
                        for name, val in summary_info.items():
                            reflection_context += f"{name}: {val}\n"
                        
                        if not reflection_context:
                            reflection_context = "(無特定輸出變數，這通常表示沒有計算出任何數據)"

                        reflection_prompt = f"""
                        你是一個嚴格的程式碼審查員 (QA)。
                        
                        1. 使用者原始問題: "{prompt}"
                        2. 強化後的問題描述: "{enhanced_prompt}"
                        3. 目前生成的程式碼:
                        ```python
                        {code_to_execute}
                        ```
                        4. 程式執行後的關鍵變數結果 (Variable State):
                        {reflection_context}
                        
                        **任務 (Critical Logic Check):**
                        請仔細檢查「變數結果」是否顯示**資料為空**或**邏輯錯誤**。
                        
                        **嚴格判斷標準:**
                        - ❌ **如果變數顯示 `Empty DataFrame`、`0 rows` 或 `[]` (空列表):** 代表篩選條件太嚴苛、名字拼錯，或是分析邏輯不適用於該資料子集。這會導致圖表空白。**必須視為失敗 (FAIL)**。
                        - ❌ **如果沒有產生 `fig` 變數:** 視為失敗。
                        - ✅ 只有當資料存在 (rows > 0) 且邏輯正確回答問題時，才回傳 PASS。
                        
                        **輸出格式 (二選一):**
                        1. 如果結果合理、資料非空且正確，請**僅輸出**字串: "PASS"
                        2. 如果發現 `Empty DataFrame` 或其他邏輯問題，請輸出**修正後的完整 Python 程式碼** (必須包含 ```python 區塊)。
                           (例如：嘗試使用 `str.contains` 進行模糊搜尋，放寬篩選條件，或改用更適合該資料量的圖表)。
                        """
                        
                        reflection_response = client.chat.completions.create(
                            model=model_choice,
                            messages=[{"role": "user", "content": reflection_prompt}],
                            temperature=0.1
                        )
                        reflection_content = reflection_response.choices[0].message.content.strip()

                        if "PASS" not in reflection_content and "```python" in reflection_content:
                            # 觸發邏輯修正
                            status.update(label="Step 4/5: AI 發現資料為空或邏輯瑕疵，正在修正程式碼...", state="running")
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
                                exec(new_code, exec_globals)
                                
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
                                pass

                        final_fig = exec_globals.get("fig", None)

                    # --- [Step 3: 確保一定有摘要資訊] ---
                    if not summary_info:
                        summary_info = {
                            "提示": "AI 未輸出可供分析的統計變數，請根據圖表與提問邏輯生成洞察。"
                        }

                    # --- [Step 4: 顯示分析內容] ---
                    if code_to_execute:
                        with st.expander("🧾 查看 AI 生成的程式碼 (最終版)", expanded=False):
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
                        st.warning("⚠️ AI 沒有輸出圖表 (可能是資料篩選後為空，建議檢查球員名稱是否正確)。")

                    # --- [Step 5: 生成數據洞察] ---
                    status.update(label="Step 5/5: 正在撰寫數據洞察...")
                    summary_text = ""
                    st.markdown("### 📊 數據洞察")
                    
                    try:
                        analysis_context_str = ""
                        if not summary_info:
                            analysis_context_str = "AI 程式碼未產生任何可供分析的摘要變數。"
                        else:
                            analysis_context_str += "程式碼執行後，擷取出以下核心變數與其值：\n\n"
                            for name, val in summary_info.items():
                                analysis_context_str += f"### 變數 `{name}` (型別: `{type(val).__name__}`)\n"
                                if isinstance(val, (pd.DataFrame, pd.Series)):
                                    analysis_context_str += f"```markdown\n{val.to_markdown()}\n```\n\n"
                                else:
                                    analysis_context_str += f"```\n{str(val)}\n```\n\n"
                        
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
                        
                        insight = client.chat.completions.create(
                            model=model_choice,
                            messages=[
                                {"role": "system", "content": "你是一位專業羽球數據分析師，請針對使用者問題與核心數據結果，撰寫精準洞察，只提供有用的資訊。"},
                                {"role": "user", "content": insight_prompt},
                            ],
                            temperature=0.4,
                        )
                        summary_text = insight.choices[0].message.content
                        st.markdown(summary_text)

                    except Exception as e:
                        summary_text = f"*(無法生成洞察: {e})*"
                        st.warning(summary_text)

                    # --- [Step 6: 儲存至歷史] ---
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

                    status.update(label="分析完成！", state="complete")

                except Exception as e:
                    status.update(label="分析失敗", state="error")
                    st.error(f"❌ 錯誤: {e}")
                    st.session_state.messages.append({
                        "role": "assistant", "content": str(e), "figure": None
                    })