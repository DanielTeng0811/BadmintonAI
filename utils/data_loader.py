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
DATA_FILE = "processed_new.csv"
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
    - 計算缺失值比例。
    - 若欄位唯一值 <= 20，列出所有唯一值。
    - 若欄位為數值型（int/float），列出最小值與最大值。

    Args:
        df: pandas DataFrame

    Returns:
        str: DataFrame 的結構資訊
    """
    # 儲存欄位分析資訊
    extra_info = []

    # 3. 逐欄分析
    for col in df.columns:
        series = df[col]
        dtype = series.dtype

        # --- 計算缺失值 ---
        missing_count = series.isna().sum()
        total_count = len(df)
        missing_pct = (missing_count / total_count) * 100

        # 加入標題 (包含欄位名稱與型態)
        extra_info.append(f"\n### 欄位 '{col}'")
        extra_info.append(f"- 型態: {dtype}")
        
        # 顯示缺失值資訊 (如果完全沒有缺失值，也可以選擇不顯示，這裡預設都會顯示)
        if missing_count > 0:
            extra_info.append(f"- ⚠️ 缺失值: {missing_pct:.2f}% ({missing_count} 筆)")
        else:
            extra_info.append(f"- 缺失值: 0% (無缺失)")

        # --- 數值欄位統計 ---
        if np.issubdtype(dtype, np.number):  # 判斷是否為數值型
            col_min = series.min(skipna=True)
            col_max = series.max(skipna=True)
            extra_info.append(f"- 數值範圍: 最小值 = {col_min}, 最大值 = {col_max}")

        # --- 唯一值資訊 ---
        num_unique = series.nunique()
        if num_unique <= 20:
            unique_vals = series.unique()
            # 處理 numpy array 轉 list 顯示比較好看
            unique_vals_list = list(unique_vals)
            extra_info.append(f"- 唯一值內容: {unique_vals_list}")

    # 5. 合併輸出內容
    final_output = (
        "[欄位詳細分析報告]"
        + "\n" + "="*60
        + "".join(extra_info)
    )

    return final_output
#  加入"場地編號對應: 前排:1-4,27,28,31,32;中排:5-16,26,30;後排:17-25,29

@st.cache_data
def load_raw_definitions(filepath):
    """載入原始 JSON 定義"""
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return None

def format_definitions(full_definitions):
    """將定義字典格式化為 Markdown 字串 (共用邏輯)"""
    if not full_definitions: return ""
    
    output_parts = []
    
    # 1. Metadata
    if "metadata" in full_definitions:
        meta = full_definitions["metadata"]
        output_parts.append("## 比賽資料結構")
        for k, v in meta.items():
            output_parts.append(f"- {k.capitalize()}: {v}")
        output_parts.append("")

    # 2. Shot Types (Always included if present)
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
        # 簡化輸出: 只顯示必要資訊
        output_parts.append(f"### `{col}`: {desc}")
        
        for k, v in item.items():
            if k in ["column", "description"]: continue
            if k in ["usage", "note", "warning", "IMPORTANT", "mapping"]:
                 output_parts.append(f"- **{k.title()}**: {v}")

    # 4. Analysis Guidelines
    if "analysis_guidelines" in full_definitions:
        output_parts.append("\n## 分析指南")
        # 這裡簡化處理，直接轉 string，省去遞迴排版
        output_parts.append(json.dumps(full_definitions["analysis_guidelines"], indent=2, ensure_ascii=False))

    return "\n".join(output_parts)

@st.cache_data
def load_column_definitions(filepath):
    """相容舊版函數: 回傳完整定義字串"""
    raw = load_raw_definitions(filepath)
    if not raw: return "錯誤：找不到定義檔。"
    return format_definitions(raw)

def get_filtered_schema_string(topics: list):
    """
    根據主題動態篩選欄位定義。
    Topics: ['spatial', 'score'] (Core is always included)
    """
    raw = load_raw_definitions(COLUMN_DEFINITION_FILE)
    if not raw: return ""
    
    # 定義欄位群組
    SPATIAL_KEYWORDS = ['_x', '_y', '_area', 'distance', 'moving']
    SCORE_KEYWORDS = ['score', 'win_reason', 'lose_reason', 'server', 'status']
    
    # 複製一份以免修改到快取
    filtered_defs = raw.copy()
    filtered_columns = []
    
    core_cols = []
    spatial_cols = []
    score_cols = []
    
    # 分類欄位
    for col_def in raw.get("data_columns", []):
        name = col_def['column']
        
        is_spatial = any(k in name for k in SPATIAL_KEYWORDS)
        is_score = any(k in name for k in SCORE_KEYWORDS)
        
        if is_spatial:
            spatial_cols.append(col_def)
        elif is_score:
            score_cols.append(col_def)
        else:
            core_cols.append(col_def) # Core 包含 match, set, rally, player, type 等
            
    # 根據 Topics 組裝
    final_cols = core_cols[:] # Core 永遠保留
    
    if 'spatial' in topics or 'all' in topics:
        final_cols.extend(spatial_cols)
    if 'score' in topics or 'all' in topics:
        final_cols.extend(score_cols)
        
    filtered_defs['data_columns'] = final_cols
    return format_definitions(filtered_defs)


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
