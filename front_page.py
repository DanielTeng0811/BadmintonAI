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
        model_choice = st.selectbox("選擇模型", ["gpt-4o-mini", "gpt-4o"], index=0)

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
if prompt := st.chat_input("請輸入你的數據分析問題..."):
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
            st.session_state.messages.append({"role": "user", "content": prompt})

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
                        clarification_check_prompt = f"""
                        檢查問題是否明確 (含球員/時間/比較對象)。
                        問題: "{prompt}"
                        欄位: {data_schema_info}
                        若不明確/有歧義/代名詞不清，需澄清。
                        
                        輸出:
                        1. 明確: CLEAR
                        2. 需澄清 JSON:
                        {{
                        "need_clarification": true,
                        "question": "請問您要...",
                        "options": ["選項1...", "選項2..."]
                        }}
                        """

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

                    # --- [Step 1: 轉化使用者問題] ---
                    status.update(label="Step 1/6: 正在釐清您的問題...")
                    
                    enhancement_system_prompt = f"""
                    你是資料分析輔助系統。請分析使用者問題。
                    任務：
                    1. 將簡短問題轉化為完整、具體的數據分析問題。
                    2. 判斷問題是否需要場地位置資訊。

                    Schema: {data_schema_info}

                    輸出 JSON 格式 (不要 Markdown):
                    {{
                        "enhanced_prompt": "完整的問題與需求描述...",
                        "needs_court_info": true/false
                    }}
                    """
                    
                    messages_1 = [
                            {"role": "system", "content": enhancement_system_prompt},
                            {"role": "user", "content": prompt}
                        ]
                    enhancement_response = client.chat.completions.create(
                        model=model_choice,
                        messages=messages_1,
                        temperature=0.2
                    )
                    
                    # 解析回應
                    raw_content = enhancement_response.choices[0].message.content.strip()
                    log_llm_interaction("Step 1: Enhancement", messages_1, raw_content)
                    enhanced_prompt = raw_content
                    needs_court_info = False

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
                    except:
                        print(f"Enhancement JSON parse failed, using raw text. Content: {raw_content[:50]}...")
                        # Fallback: 如果解析失敗，假設不需要場地資訊，或者如果關鍵字出現則設為True
                        if any(k in prompt for k in ["落點", "位置", "區域", "座標", "location", "area"]):
                            needs_court_info = True

                    print(f"Enhanced Prompt: {enhanced_prompt}")
                    print(f"Needs Court Info: {needs_court_info}")

                    # --- [Step 2: 生成分析程式碼] ---
                    status.update(label="Step 2/6: 正在生成分析程式碼...")
                    system_prompt = create_system_prompt(data_schema_info, column_definitions_info)
                    
                    # 動態注入場地資訊
                    if needs_court_info and court_place_info:
                        system_prompt += f"\n\n**場地位置參考資訊 (Court Grid Definitions):**\n{court_place_info}\n"

                    # [修改點]：注入通用且穩健的視覺化指導原則，而非強制特定方法
                    system_prompt += """
                    \n**最佳實踐:**
                    1. 區分連續數值(Float)與類別。座標勿直接 groupby。
                    2. 軸標籤避免大量浮點數。
                    3. 繪圖前檢查 `if len(filtered_df) > 0:`。
                    """

                    conversation = [{"role": "system", "content": system_prompt}]
                    if len(st.session_state.messages) > 1:
                        for m in st.session_state.messages[:-1]:
                            # 跳過澄清相關的對話（包含 🤔 emoji 的訊息）
                            if m.get("content") and "🤔" not in m.get("content", ""):
                                conversation.append({"role": m["role"], "content": m["content"]})
                    
                    conversation.append({"role": "user", "content": enhanced_prompt})

                    response = client.chat.completions.create(
                        model=model_choice, messages=conversation
                    )
                    ai_response = response.choices[0].message.content
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
                    
                    if code_to_execute:
                        execution_output = ""
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
                                    exec(code_to_execute, exec_globals)
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

                        # --- [Step 4: 邏輯反饋與修正 (Logic Reflection Loop)] ---
                        status.update(label="Step 4/6: AI 正在檢查分析結果的邏輯性...")
                        
                        reflection_context = ""
                        for name, val in summary_info.items():
                            reflection_context += f"{name}: {val}\n"
                        
                        if not reflection_context:
                            reflection_context = "(無特定輸出變數，這通常表示沒有計算出任何數據)"

                        reflection_prompt = f"""
                        QA Check:
                        1. 問題: "{prompt}" (強化: "{enhanced_prompt}")
                        2. 程式:
                        ```python
                        {code_to_execute}
                        ```
                        3. 結果 (Stdout): {execution_output}
                        4. 變數: {reflection_context}
                        
                        判斷:
                        - ❌ 變數顯示 `Empty/0 rows` 或 `_generated_figures_count`=0 且無輸出 -> FAIL
                        - ✅ 資料非空且有輸出/圖表 -> PASS
                        
                        回覆: "PASS" 或 修正後的程式碼 (含 ```python)。
                        """
                        
                        messages_4 = [{"role": "user", "content": reflection_prompt}]
                        reflection_response = client.chat.completions.create(
                            model=model_choice,
                            messages=messages_4,
                            temperature=0.1
                        )
                        reflection_content = reflection_response.choices[0].message.content.strip()
                        log_llm_interaction("Step 4: Logic Reflection", messages_4, reflection_content)

                        if "PASS" not in reflection_content and "```python" in reflection_content:
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
                                    exec(new_code, exec_globals)
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
                        
                        insight_prompt = f"""
                        你是羽球教練。
                        問題: "{prompt}"
                        數據:
                        {analysis_context_str}
                        """

                        if needs_court_info and court_place_info:
                            insight_prompt += f"\n場地定義參考:\n{court_place_info}\n"

                        insight_prompt += """
                        用教練口吻，基於數據精簡提供戰術洞察。說明數字背後的意義，不要只唸數字，勿過度解讀，只說正確的事實。
                        """
                        
                        
                        messages_6 = [
                                {"role": "system", "content": "你是一位專業羽球教練與數據戰術大師。請針對使用者問題與核心數據結果，用教練的口吻撰寫精準的戰術洞察，提供有深度的分析，需精簡回答。"},
                                {"role": "user", "content": insight_prompt},
                            ]
                        insight = client.chat.completions.create(
                            model=model_choice,
                            messages=messages_6,
                            temperature=0.4,
                        )
                        summary_text = insight.choices[0].message.content
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
                    })

                    status.update(label="分析完成！", state="complete")

                except Exception as e:
                    status.update(label="分析失敗", state="error")
                    st.error(f"❌ 錯誤: {e}")
                    st.session_state.messages.append({
                        "role": "assistant", "content": str(e), "figure": None
                    })