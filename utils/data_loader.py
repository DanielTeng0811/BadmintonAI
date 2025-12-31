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
DATA_FILE = "processed_new_3.csv"
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
    Features:
    - Column Type & Missing (Null) Percentage
    - Numeric Range (Min/Max)
    - Unique Values (if <= 20)
    """
    schema_parts = []
    schema_parts.append(f"Total Rows: {len(df)}")
    schema_parts.append("="*60)

    for col in df.columns:
        series = df[col]
        dtype = series.dtype
        null_count = series.isnull().sum()
        null_pct = (null_count / len(df)) * 100
        
        # Header: Name (Type) | Empty: X.X%
        col_header = f"### `{col}` ({dtype}) | Empty: {null_pct:.1f}%"
        schema_parts.append(col_header)

        # 1. Numeric Range
        if np.issubdtype(dtype, np.number):
            col_min = series.min(skipna=True)
            col_max = series.max(skipna=True)
            schema_parts.append(f"- Range: {col_min} ~ {col_max}")

        # 2. Unique Values (Cardinality check)
        num_unique = series.nunique()
        if num_unique <= 20:
            unique_vals = series.unique()
            # Convert numpy array to list for clean printing
            val_list = unique_vals.tolist() if hasattr(unique_vals, 'tolist') else list(unique_vals)
            # Filter out extensive output if list is still too long/messy (optional safety)
            schema_parts.append(f"- Values: {val_list}")
            
    return "\n".join(schema_parts)
#  加入"場地編號對應: 前排:1-4,27,28,31,32;中排:5-16,26,30;後排:17-25,29

@st.cache_data
def load_column_definitions(filepath):
    """
    載入並格式化欄位定義（支援新的結構化格式）
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            full_definitions = json.load(f)

        output_parts = []

        # 1. Metadata
        if "metadata" in full_definitions:
            meta = full_definitions["metadata"]
            output_parts.append("## 比賽資料結構")
            for k, v in meta.items():
                output_parts.append(f"- {k.capitalize()}: {v}")
            output_parts.append("")

        # 2. Shot Types
        if "shot_types" in full_definitions:
            output_parts.append("## 球種代碼對照表")
            for code, name in full_definitions["shot_types"].items():
                output_parts.append(f"- {code}: {name}")
            output_parts.append("")

        # 3. Data Columns
        output_parts.append("## 欄位定義")
        for item in full_definitions.get("data_columns", []):
            col = item.get("column", "Unknown")
            desc = item.get("description", "")
            output_parts.append(f"### `{col}`")
            output_parts.append(f"**說明**: {desc}")
            
            # Generic loop for other attributes
            for k, v in item.items():
                if k in ["column", "description"]: continue
                
                label = k.replace("_", " ").title()
                if k == "warning" or k == "IMPORTANT":
                    output_parts.append(f"- ⚠️ **{label}**: {v}")
                else:
                    output_parts.append(f"- **{label}**: {v}")

        # 4. Analysis Guidelines
        if "analysis_guidelines" in full_definitions:
            output_parts.append("\n## 分析指南")
            guidelines = full_definitions["analysis_guidelines"]
            
            def format_guideline(key, val, level=0):
                indent = "  " * level
                prefix = "- " if level > 0 else "### "
                label = key.replace("_", " ").title()
                
                if isinstance(val, dict):
                    lines = [f"{indent}{prefix}{label}"]
                    for sub_k, sub_v in val.items():
                        lines.append(format_guideline(sub_k, sub_v, level + 1))
                    return "\n".join(lines)
                else:
                    return f"{indent}- **{label}**: {val}"

            for k, v in guidelines.items():
                output_parts.append(format_guideline(k, v))

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
    
    # 預設值 (若無資料)
    data_schema_info = ""
    column_definitions_info = ""

    if df is not None and not df.empty:
        # [Dynamic Column Renaming]
        # 根據第一筆資料的 player/opponent 決定欄位名稱
        # 假設資料已排序: match_id -> set -> rally -> ball_round
        try:
            first_row = df.iloc[0]
            p1_name = first_row['player'] # 第一球的打擊者 (Player A)
            p2_name = first_row['opponent'] # 對手 (Player B)
            
            # 2. Update Definitions String (Dynamic)
            # 因為 data_processor 已經將 CSV 的欄位改為 {Name}_score
            # 我們需要偵測欄位名稱來更新 definition string
            # 偵測邏輯：找出所有以 "_score" 結尾且不是 "player" 或 "opponent" 的欄位
            
            score_cols = [c for c in df.columns if c.endswith('_score')]
            
            # 簡單策略：如果找到 2 個分數欄位，嘗試替換
            if len(score_cols) >= 2:
                # 假設順序通常是 P1, P2 (或根據資料分布)
                # 這裡我們嘗試找出如果不叫 'player_score' 或 'opponent_score' 的那些
                custom_score_cols = [c for c in score_cols if c not in ['player_score', 'opponent_score']]
                
                if len(custom_score_cols) == 2:
                    # 更新 definition string
                    # 注意：原 JSON 是 player_score / opponent_score
                    # 我們分別用前兩個找到的取代之
                     column_definitions_info = column_definitions_info.replace("player_score", custom_score_cols[0])
                     column_definitions_info = column_definitions_info.replace("opponent_score", custom_score_cols[1])
            
            # 3. Generate Schema from the MODIFIED DataFrame
            data_schema_info = get_data_schema(df)
            
        except Exception as e:
            print(f"Error during dynamic renaming: {e}")
            # Fallback
            data_schema_info = get_data_schema(df)
            column_definitions_info = load_column_definitions(COLUMN_DEFINITION_FILE)
            
    else:
        data_schema_info = "錯誤：找不到 `all_dataset.csv` 或資料為空。"
        column_definitions_info = load_column_definitions(COLUMN_DEFINITION_FILE)

    return df, data_schema_info, column_definitions_info
