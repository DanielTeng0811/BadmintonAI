"""
資料載入相關函數
Data loading utilities for BadmintonAI
"""
import os
import pandas as pd
import json
import io
import streamlit as st


# 檔案路徑常數
DATA_FILE = "all_dataset.csv"
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
    從 DataFrame 獲取欄位型態資訊

    Args:
        df: pandas DataFrame

    Returns:
        str: DataFrame 的結構資訊（欄位名稱、型態等）
    """
    buffer = io.StringIO()
    df.info(buf=buffer)
    return buffer.getvalue()


@st.cache_data
def load_column_definitions(filepath):
    """
    載入並格式化欄位定義

    Args:
        filepath: 欄位定義 JSON 檔案路徑

    Returns:
        str: 格式化後的欄位定義文字（Markdown 格式）
    """
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
