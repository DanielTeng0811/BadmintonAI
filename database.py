"""
資料庫處理模組 - 負責 CSV 與 SQLite 的轉換和操作
"""

import pandas as pd
import sqlite3
from config import CSV_FILE, DB_FILE, TABLE_NAME


def csv_to_sqlite(csv_file=CSV_FILE, db_file=DB_FILE, table_name=TABLE_NAME):
    """
    將 CSV 檔案轉換成 SQLite 資料庫

    Args:
        csv_file: CSV 檔案路徑
        db_file: 資料庫檔案路徑
        table_name: 表格名稱
    """
    # 讀取 CSV 檔案
    df = pd.read_csv(csv_file)

    # 建立或連線 SQLite 資料庫
    conn = sqlite3.connect(db_file)

    # 將 CSV 存成一張表格
    df.to_sql(table_name, conn, if_exists="replace", index=False)

    print(f"✅ CSV 已成功存入 SQLite 資料庫 {db_file} 的 {table_name} 表格")

    # 關閉連線
    conn.close()


def show_sample_data(db_file=DB_FILE, table_name=TABLE_NAME, limit=5):
    """
    顯示資料庫中的範例資料

    Args:
        db_file: 資料庫檔案路徑
        table_name: 表格名稱
        limit: 顯示的資料筆數
    """
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    cursor.execute(f"SELECT * FROM {table_name} LIMIT {limit};")
    rows = cursor.fetchall()

    print(f"前 {limit} 筆資料：")
    for row in rows:
        print(row)

    conn.close()


def execute_query(sql_query, db_file=DB_FILE):
    """
    執行 SQL 查詢

    Args:
        sql_query: SQL 查詢語句
        db_file: 資料庫檔案路徑

    Returns:
        查詢結果
    """
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    try:
        cursor.execute(sql_query)
        results = cursor.fetchall()
        conn.close()
        return results
    except Exception as e:
        conn.close()
        raise e


if __name__ == "__main__":
    # 測試功能
    csv_to_sqlite()
    show_sample_data()
