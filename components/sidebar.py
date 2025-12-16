import streamlit as st
import io
import zipfile
from datetime import datetime
from utils.app_utils import get_api_key

def render_sidebar():
    """
    渲染側邊欄並回傳設定值
    """
    settings = {}
    
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
        settings["api_mode"] = api_mode
        settings["api_key_input"] = api_key_input

        if api_mode == "Gemini":
            model_choice = st.selectbox("選擇模型",["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"], index=0)
        else:
            model_choice = st.selectbox("選擇模型", ["gpt-4o-mini", "gpt-4o"], index=1)
        settings["model_choice"] = model_choice

        st.divider()

        # 多輪問答開關
        enable_clarification = st.checkbox("啟用多輪問答（問題不明確時會主動詢問）", value=False)
        settings["enable_clarification"] = enable_clarification

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

    return settings
