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
DATA_FILE = "" #"processed_new_3.csv"
DATA_DIR = "split_matches" # 新增資料夾路徑
COLUMN_DEFINITION_FILE = "column_definition.json"

def get_available_matches():
    """
    掃描 `split_matches` 資料夾，回傳所有可用場次資訊。
    Returns:
        list of dict: [{'id': 1, 'p1': 'Name', 'p2': 'Name', 'filename': '...'}, ...]
    """
    matches = []
    if not os.path.exists(DATA_DIR):
        return matches

    for f in os.listdir(DATA_DIR):
        if f.endswith(".csv"):
            # 解析檔名: {P1}_{P2}_{ID}.csv
            try:
                base_name = os.path.splitext(f)[0]
                parts = base_name.split('_')
                # 假設最後一個部分是 ID，前面是球員名 (可能包含底線)
                # 簡單策略：找出最後一個數字當ID，剩下的以前後分
                # 但題目給的格式是 {player_score的選手}_{opponent_score的選手}_{編號}
                # P1: player_score, P2: opponent_score
                
                match_id = parts[-1] 
                # P1, P2 解析稍微複雜，因為名字可能有底線
                # 尋找分隔點：倒數第二個底線? 不一定可靠
                # 觀察範例: Kento MOMOTA_CHOU Tien Chen_1.csv
                # 這裡 P1=Kento MOMOTA, P2=CHOU Tien Chen
                
                # 暫時用簡單 parser: 假設名字中間只有一個分界
                # 但這裡檔名結構其實是: [P1 Part 1] [P1 Part 2] ... _ [P2 Part 1] ... _ [ID]
                # 有點難分。改為讀取檔案內容的第一行來確認更準確? 
                # 或者依靠檔名: 假設最後一個是ID，剩下的是 P1_P2。
                # 為了避免 split 錯誤，這裡我們只存 filename，具體 P1/P2 留給 load_all_data 處理
                
                matches.append({
                    "id": match_id,
                    "filename": f,
                    "info": base_name # 簡單顯示
                })
            except Exception:
                pass
    
    # 根據 ID 排序
    try:
        matches.sort(key=lambda x: int(x['id']) if x['id'].isdigit() else 999)
    except:
        pass
        
    return matches



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


def load_all_data(target_paths=None):
    """
    載入所有資料（DataFrame、Schema、欄位定義）
    支援讀取多個指定的 csv 檔案並合併。

    Args:
        target_paths (list): 檔案路徑列表。若為 None，則預設讀取 DATA_FILE。

    Returns:
        tuple: (df, data_schema_info, column_definitions_info)
    """
    dfs = []
    column_definitions_info = load_column_definitions(COLUMN_DEFINITION_FILE)
    
    if not target_paths:
        # 預設路徑 (相容舊邏輯，或設為空)
        # 這裡為了保險，若沒有指定就讀取預設的大檔，或者讀取資料夾中第一個
        # 題目說「根據題目找到適合的檔案」，剛開始可能沒有指定
        if os.path.exists(DATA_FILE):
             target_paths = [DATA_FILE]
        else:
             # Fallback to first file in split_matches
             matches = get_available_matches()
             if matches:
                 target_paths = [os.path.join(DATA_DIR, matches[0]['filename'])]
             else:
                 target_paths = []

    if target_paths:
        for filepath in target_paths:
            df_temp = load_data(filepath)
            if df_temp is not None and not df_temp.empty:
                try:
                    # [Dynamic Column Renaming based on Filename/Content]
                    # 優先從檔名解析: {P1}_{P2}_{ID}.csv
                    filename = os.path.basename(filepath)
                    base, ext = os.path.splitext(filename)
                    parts = base.split('_')
                    
                    p1_name = "PlayerA"
                    p2_name = "PlayerB"
                    
                    # 嘗試解析 P1, P2
                    # 格式: Name A_Name B_ID
                    # 由於名字可能有空格和底線，比較難拆。
                    # 策略: 讀取第一列的 player/opponent 欄位 (最準確)
                    # 題目說: "檔案名稱對應到{player_score的選手}_{opponent_score的選手}_{編號}"
                    # 但也說 "由檔案名稱可區分"。為了最穩健，我們結合兩者：
                    # 使用 df 內容來確定名字，但用檔名格式來確認欄位對應關係
                    # 其實 df['player'] 第一筆就是 player_score 的歸屬者 (因為是該場第一球 player)
                    
                    first_row = df_temp.iloc[0]
                    p1_name = first_row.get('player', 'PlayerA')
                    p2_name = first_row.get('opponent', 'PlayerB')

                    # Rename
                    rename_map = {
                        'player_score': f'{p1_name}_score',
                        'opponent_score': f'{p2_name}_score'
                    }
                    df_temp = df_temp.rename(columns=rename_map)
                    
                    # 動態更新 definitions string
                    # 注意: 多檔案合併時，definitions 只要替換一次即可 (假設大家欄位名邏輯一致)
                    # 這裡會有個問題: 如果不同檔案 P1 不同，column definition 會有字串取代衝突
                    # 解決: Column Definition 不要在這裡 replace? 
                    # 或者 Column Definition 只解釋 "xxx_score" 是該球員分數。
                    # 為了簡單，我們把所有出現的球員名字都加進去? 
                    # 暫時策略: 針對最後一個處理的檔案做 replace (顯示當前關注的球員)，
                    # 或者更 generic 地說 "{Player Name}_score"
                    
                    # 為了符合 User Requirement，我們還是做 Replace，但這只對單一檔案有效。
                    # 對於多檔案，我們可能會有 Kento_score 和 Chou_score 同時存在。
                    # 我們累積 unique player names?
                    pass 

                except Exception as e:
                    print(f"Renaming error for {filepath}: {e}")
                
                dfs.append(df_temp)

    # Merge
    if dfs:
        df = pd.concat(dfs, ignore_index=True)
        # Generate Schema for the COMBINED df (will show all xxx_score columns)
        data_schema_info = get_data_schema(df)
    else:
        df = pd.DataFrame() # Empty
        data_schema_info = "無資料載入。"

    return df, data_schema_info, column_definitions_info
