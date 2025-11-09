"""
資料載入相關函數
Data loading utilities for BadmintonAI
"""
import os
import pandas as pd
import json
import io
import streamlit as st
import numpy as np

# 檔案路徑常數
DATA_FILE = "processed_data.csv"
COLUMN_DEFINITION_FILE = "column_definition.json"


@st.cache_data
def load_data(filepath):
    """
    載入 CSV 數據並快取

    Args:
        filepath: CSV 檔案路徑

    Returns:
        pd.DataFrame or None: 載入的 DataFrame，若檔案不存在則回傳 None
    """
    if os.path.exists(filepath):
        return pd.read_csv(filepath)
    return None


@st.cache_data
def get_data_schema(df):
    """
    從 DataFrame 獲取欄位型態資訊。
    額外功能：
    - 若欄位唯一值 <= 20，列出所有唯一值。
    - 若欄位為數值型（int/float），列出最小值與最大值。

    Args:
        df: pandas DataFrame

    Returns:
        str: DataFrame 的結構資訊（欄位名稱、型態、唯一值、數值範圍等）
    """
    # 1. 取得 df.info() 的基本資訊
    buffer = io.StringIO()
    df.info(buf=buffer)
    schema_info = buffer.getvalue()

    # 2. 儲存額外欄位分析資訊
    extra_info = []

    # 3. 逐欄分析
    for col in df.columns:
        series = df[col]
        dtype = series.dtype

        # --- 數值欄位統計 ---
        if np.issubdtype(dtype, np.number):  # 判斷是否為數值型
            col_min = series.min(skipna=True)
            col_max = series.max(skipna=True)
            extra_info.append(f"\n### 欄位 '{col}' 數值範圍:")
            extra_info.append(f"最小值 = {col_min}, 最大值 = {col_max}")

        # --- 唯一值資訊 ---
        num_unique = series.nunique()
        if num_unique <= 20:
            unique_vals = series.unique()
            unique_vals_list = list(unique_vals)
            extra_info.append(f"\n### 欄位 '{col}' (唯一值 <= 20 個):")
            extra_info.append(f"{unique_vals_list}")

    # 4. 新增固定的場地編號對應資訊
    court_mapping_info = (
        "\n" + "="*60
        + "\n[場地編號對應 (參考用)]"
        + "\n" + "="*60
        + "\n前排: 1-4, 27, 28, 31, 32"
        + "\n中排: 5-16, 26, 30"
        + "\n後排: 17-25, 29"
    )

    # 5. 合併輸出內容 (已修正)
    final_output = (
        schema_info
        + court_mapping_info  # 插入場地資訊
        + "\n" + "="*60  # <-- 修正：移除了多餘的 's'
        + "\n[欄位額外資訊 (動態分析)]" # 修改標題以區分
        + "\n" + "="*60
        + "".join(extra_info)
    )

    return final_output
#  加入"場地編號對應: 前排:1-4,27,28,31,32;中排:5-16,26,30;後排:17-25,29

@st.cache_data
def load_column_definitions(filepath):
    """
    載入並格式化欄位定義（支援新的結構化格式）

    Args:
        filepath: 欄位定義 JSON 檔案路徑

    Returns:
        str: 格式化後的欄位定義文字（Markdown 格式）
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            full_definitions = json.load(f)

        # 建立格式化輸出
        output_parts = []

        # 1. 添加 metadata 資訊
        if "metadata" in full_definitions:
            metadata = full_definitions["metadata"]
            output_parts.append("## 比賽資料結構")
            output_parts.append(f"- 比賽形式：{metadata.get('match_structure', {}).get('format', '')}")
            output_parts.append(f"- 計分方式：{metadata.get('match_structure', {}).get('set_scoring', '')}")
            output_parts.append(f"- 球員：{', '.join(metadata.get('players', []))}")
            if 'data_recording_note' in metadata:
                output_parts.append(f"\n{metadata['data_recording_note']}")
            output_parts.append("")

        # 2. 添加球種定義
        if "shot_types" in full_definitions:
            output_parts.append("## 球種代碼對照表")
            shot_types = full_definitions["shot_types"]
            for code, info in shot_types.items():
                output_parts.append(f"- {code}: {info['name']} ({info['english']})")
            output_parts.append("")

        # 3. 添加欄位定義（結構化格式）
        output_parts.append("## 欄位定義")
        column_definitions = full_definitions.get("data_columns", [])
        for item in column_definitions:
            col_name = item.get('column', '')
            desc = item.get('description', '')

            # 基本資訊
            output_parts.append(f"\n### `{col_name}`")
            output_parts.append(f"**說明**：{desc}")

            # 資料類型與值域
            if 'data_type' in item:
                output_parts.append(f"- **資料類型**：{item['data_type']}")
            if 'value_range' in item:
                val_range = item['value_range']
                if isinstance(val_range, list):
                    output_parts.append(f"- **可能值**：{', '.join(val_range)}")
                else:
                    output_parts.append(f"- **值域**：{val_range}")

            # 粒度層級
            if 'granularity' in item:
                output_parts.append(f"- **粒度**：{item['granularity']}")

            #空間分布
            if 'area_definition' in item:
                output_parts.append(f"- **場地區塊分布**：{item['area_definition']}")
            # 計算方式
            if 'calculation' in item:
                output_parts.append(f"- **計算方式**：{item['calculation']}")

            # 關聯欄位
            if 'related_to' in item and item['related_to']:
                related = ', '.join([f'`{r}`' for r in item['related_to']])
                output_parts.append(f"- **關聯欄位**：{related}")

            # 使用情境
            if 'usage' in item:
                output_parts.append(f"- **用途**：{item['usage']}")

            # 重要提醒
            if 'important_note' in item:
                output_parts.append(f"- ⚠️ **重要**：{item['important_note']}")

            # 正確用法
            if 'correct_usage' in item:
                output_parts.append(f"- ✅ **正確用法**：`{item['correct_usage']}`")

            # 錯誤用法
            if 'wrong_usage' in item:
                output_parts.append(f"- ❌ **錯誤用法**：`{item['wrong_usage']}`")

        # 4. 添加分析指南
        if "analysis_guidelines" in full_definitions:
            output_parts.append("\n## 分析指南")
            guidelines = full_definitions["analysis_guidelines"]

            for guide_name, guide_info in guidelines.items():
                # 轉換 snake_case 為中文標題
                title_map = {
                    "rally_counting": "回合計數",
                    "win_rate_calculation": "勝率計算",
                    "player_name_usage": "球員名稱使用",
                    "shot_type_analysis": "球種分析",
                    "lose_reason_filter": "失誤原因篩選",
                    "win_reason_filter": "得分方式篩選",
                    "match_score_query": "比賽比分查詢"
                }
                title = title_map.get(guide_name, guide_name)
                output_parts.append(f"\n### {title}")

                for key, value in guide_info.items():
                    if key == "issue":
                        output_parts.append(f"- **問題**：{value}")
                    elif key == "context":
                        output_parts.append(f"- **情境**：{value}")
                    elif key == "data_limitation":
                        output_parts.append(f"- {value}")
                    elif key == "correct_method" or key == "correct":
                        if isinstance(value, list):
                            output_parts.append(f"- ✅ **正確**：{', '.join(value)}")
                        else:
                            output_parts.append(f"- ✅ **正確方法**：`{value}`")
                    elif key == "wrong_method" or key == "wrong":
                        if isinstance(value, list):
                            output_parts.append(f"- ❌ **錯誤**：{', '.join(value)}")
                        else:
                            output_parts.append(f"- ❌ **錯誤方法**：`{value}`")
                    elif key.startswith("step"):
                        output_parts.append(f"- **{key.upper()}**：{value}")
                    elif key == "purpose":
                        output_parts.append(f"- **目的**：{value}")
                    elif key == "explanation":
                        output_parts.append(f"- **說明**：{value}")
                    elif key == "rule":
                        output_parts.append(f"- **規則**：{value}")
                    elif key == "example_code":
                        output_parts.append(f"- **程式碼範例**：```python\n{value}\n```")
                    elif key == "important_note":
                        output_parts.append(f"- ⚠️ **重要提醒**：{value}")
                    elif key == "visualization":
                        output_parts.append(f"- **視覺化建議**：{value}")
                    elif key == "note":
                        output_parts.append(f"- **備註**：{value}")
                    elif key == "data_format":
                        output_parts.append(f"- **資料格式**：{value}")
                    elif key == "alternative":
                        output_parts.append(f"- **替代方案**：{value}")

        return "\n".join(output_parts)

    except FileNotFoundError:
        return "錯誤：找不到 'column_definition.json' 檔案。"
    except json.JSONDecodeError:
        return "錯誤：'column_definition.json' 檔案格式錯誤。"


def load_all_data():
    """
    載入所有資料（DataFrame、Schema、欄位定義）

    Returns:
        tuple: (df, data_schema_info, column_definitions_info)
    """
    df = load_data(DATA_FILE)

    if df is not None:
        data_schema_info = get_data_schema(df)
        column_definitions_info = load_column_definitions(COLUMN_DEFINITION_FILE)
    else:
        data_schema_info = "錯誤：找不到 `all_dataset.csv`，請先準備好數據檔案。"
        column_definitions_info = load_column_definitions(COLUMN_DEFINITION_FILE)

    return df, data_schema_info, column_definitions_info
