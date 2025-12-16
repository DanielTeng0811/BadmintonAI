import streamlit as st
import io
from datetime import datetime
import matplotlib.pyplot as plt

# Import Steps
from logic.steps.step0_clarification import check_clarification
from logic.steps.step1_enhancement import enhance_prompt
from logic.steps.step2_code_gen import generate_code
from logic.steps.step3_execution import execute_and_fix
from logic.steps.step4_reflection import check_logic_and_fix
from logic.steps.step6_insight import generate_insights

def process_user_query(prompt, client, model_choice, df, data_schema_info, enable_clarification, use_history):
    """
    處理使用者查詢的核心邏輯流程 (Orchestrator)
    """
    
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.status("AI 數據分析師正在處理中...") as status:
            try:
                # --- [Step 0: 問題檢查與澄清] ---
                status.update(label="Step 0/6: 檢查問題是否需要澄清...")
                clarification_data = check_clarification(client, model_choice, prompt, data_schema_info, enable_clarification)
                
                if clarification_data:
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
                    return # 中斷執行

                # --- [Step 1: 轉化使用者問題] ---
                status.update(label="Step 1/6: 正在釐清您的問題...")
                enhanced_prompt, relevant_topics, needs_court_info, _ = enhance_prompt(client, model_choice, prompt)
                print(f"Enhanced Prompt: {enhanced_prompt}")
                print(f"Topics: {relevant_topics}")

                # --- [Step 2: 生成分析程式碼] ---
                status.update(label="Step 2/6: 正在生成分析程式碼...")
                code_to_execute, conversation = generate_code(
                    client, model_choice, enhanced_prompt, data_schema_info, 
                    relevant_topics, needs_court_info, use_history
                )

                # --- [Step 3: 執行程式] ---
                status.update(label="Step 3/6: 正在執行程式碼...")
                
                if code_to_execute:
                    # status.update is passed as a wrapper lambda to match signature expected by step3
                    def update_status(label, state=None):
                        status.update(label=label, state=state)
                        
                    success, code_to_execute, execution_output, exec_globals, last_error = execute_and_fix(
                        client, model_choice, code_to_execute, df, conversation, status_updater=update_status
                    )
                    
                    if not success:
                        raise last_error

                    # --- [Step 4: 邏輯反饋與修正] ---
                    status.update(label="Step 4/6: AI 正在檢查分析結果的邏輯性...")
                    
                    code_to_execute, execution_output, summary_info, final_figs = check_logic_and_fix(
                        client, model_choice, prompt, code_to_execute, execution_output, exec_globals, df, status_updater=update_status
                    )
                else:
                    execution_output = ""
                    summary_info = {}
                    final_figs = []

                # --- [Step 5: 顯示分析內容 (UI)] ---
                if not summary_info:
                    summary_info = {
                        "提示": "AI 未輸出可供分析的統計變數，請根據圖表與提問邏輯生成洞察。"
                    }

                if code_to_execute:
                    with st.expander("🧠 查看 AI 優化後的提問邏輯 (Step 1)", expanded=False):
                        st.markdown(f"**優化導引 (Enhanced Prompt):**\n{enhanced_prompt}")

                    with st.expander("🧾 查看 AI 生成的程式碼 (最終版)", expanded=False):
                        # 確保 code_to_execute 是字串
                        st.code(str(code_to_execute), language="python")

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

                summary_text = generate_insights(client, model_choice, prompt, execution_output, summary_info)
                st.markdown(summary_text)

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
                    "enhanced_prompt": enhanced_prompt
                })

                status.update(label="分析完成！", state="complete")

            except Exception as e:
                status.update(label="分析失敗", state="error")
                st.error(f"❌ 錯誤: {e}")
                # Print stack trace to console for debugging
                import traceback
                traceback.print_exc()
                
                st.session_state.messages.append({
                    "role": "assistant", "content": str(e), "figure": None
                })
