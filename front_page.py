import streamlit as st
import openai
import os
import pandas as pd
import json
import io
from dotenv import load_dotenv

# --- 初始設定與環境變數載入 ---
load_dotenv()

# 設定頁面
st.set_page_config(
    page_title="羽球 AI 數據分析師",
    page_icon="🏸",
    layout="wide"
)

# --- 資料載入與快取 ---
DATA_FILE = "all_dataset.csv"
COLUMN_DEFINITION_FILE = "column_definition.json"

@st.cache_data
def load_data(filepath):
    """載入 CSV 數據並快取"""
    if os.path.exists(filepath):
        return pd.read_csv(filepath)
    return None

@st.cache_data
def get_data_schema(df):
    """從 DataFrame 獲取欄位型態資訊"""
    buffer = io.StringIO()
    df.info(buf=buffer)
    return buffer.getvalue()

@st.cache_data
def load_column_definitions(filepath):
    """載入並格式化欄位定義"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            full_definitions = json.load(f)
        
        column_definitions = full_definitions.get("data_columns", [])
        
        if isinstance(column_definitions, list) and all(
            isinstance(item, dict) and 'column' in item and 'definition' in item
            for item in column_definitions
        ):
            return "\n".join(
                [f"- `{item['column']}`: {item['definition']}" for item in column_definitions]
            )
        else:
            return "錯誤：'column_definition.json' 的 'data_columns' 格式不符合預期。"
    except FileNotFoundError:
        return "錯誤：找不到 'column_definition.json' 檔案。"
    except json.JSONDecodeError:
        return "錯誤：'column_definition.json' 檔案格式錯誤。"

# 載入資料
df = load_data(DATA_FILE)
if df is not None:
    data_schema_info = get_data_schema(df)
    column_definitions_info = load_column_definitions(COLUMN_DEFINITION_FILE)
else:
    data_schema_info = "錯誤：找不到 `all_dataset.csv`，請先準備好數據檔案。"
    column_definitions_info = load_column_definitions(COLUMN_DEFINITION_FILE)


# --- System Prompt 產生器 ---
def create_system_prompt():
    """建立給 LLM 的系統指令"""
    return f"""
你是一位頂尖的羽球數據科學家。
你的任務是根據使用者提出的問題，生成一段 Python 程式碼來分析一個已經載入的 pandas DataFrame `df`，並繪製出能回答該問題的視覺化圖表。

**數據資訊:**
1.  **DataFrame Schema (資料欄位與型態):**
{data_schema_info}
2.  **欄位定義:**
{column_definitions_info}

**你的程式碼必須嚴格遵守以下規則:**
1.  程式碼必須使用 `matplotlib` 或 `seaborn` 函式庫來繪圖。
2.  **絕對不要** 包含 `pd.read_csv()` 或任何讀取資料的程式碼，因為 `df` 已經存在於執行環境中。
3.  程式碼的最終結果**必須**是一個 Matplotlib 的 Figure 物件，並將其賦值給一個名為 `fig` 的變數。例如：`fig, ax = plt.subplots()`。
4.  **絕對不要** 在程式碼中使用 `plt.show()`，Streamlit 會負責處理圖表的顯示。
5.  在程式碼中妥善處理中文字體顯示問題，使用 `plt.rcParams['font.sans-serif'] = ['Microsoft JhengHei']` 或其他合適的字體設定。
6.  你的回覆應包含兩個部分：
    -   一個簡短的文字說明，解釋你將如何分析以及圖表的意涵。
    -   一個 Python 程式碼區塊 (```python ... ```)，其中包含繪圖程式碼。
"""

# --- AI Client 初始化 ---
# (這部分與您原本的程式碼相同)
def initialize_client(api_mode, api_key):
    """根據模式和金鑰初始化 AI client"""
    if api_mode == "Gemini":
        return openai.OpenAI(
            api_key=api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
        )
    elif api_mode == "交大伺服器":
        return openai.OpenAI(
            api_key=api_key,
            base_url="https://llm.nycu-adsl.cc"
        )
    else:  # OpenAI 官方
        return openai.OpenAI(api_key=api_key)


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
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if "figure" in message and message["figure"] is not None:
            st.pyplot(message["figure"])


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
                    system_prompt = create_system_prompt()
                    
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
                        exec_globals = {
                            "pd": pd,
                            "st": st,
                            "df": df.copy() # 使用副本以防意外修改
                        }
                        
                        # 執行程式碼
                        exec(code_to_execute, exec_globals)
                        
                        # 從執行環境中獲取圖表物件
                        if 'fig' in exec_globals:
                            final_fig = exec_globals['fig']
                            st.pyplot(final_fig)
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
