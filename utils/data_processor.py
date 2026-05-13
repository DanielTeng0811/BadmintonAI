import pandas as pd
import numpy as np
import sqlite3
from pathlib import Path
from utils.paths import PROCESSED_CSV, PROCESSED_DB, RAW_DATA_CSV, ensure_runtime_dirs


REQUIRED_COLUMNS = ['match_id', 'set', 'rally_id', 'player', 'type', 'getpoint_player']
RELATIVE_SCORE_COLUMNS = ['player_score', 'opponent_score']


def _validate_required_columns(df):
    missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing_cols:
        raise ValueError(f"資料缺少必要欄位: {missing_cols}")


def _increment_score(last_row, winner):
    """
    Increment score in either relative score columns or winner-specific columns.
    """
    if pd.isna(winner):
        return last_row

    winner_score_col = f"{winner}_score"
    if winner_score_col in last_row.index:
        target_col = winner_score_col
    elif all(col in last_row.index for col in RELATIVE_SCORE_COLUMNS):
        if winner == last_row.get('player'):
            target_col = 'player_score'
        elif winner == last_row.get('opponent'):
            target_col = 'opponent_score'
        else:
            print(f"Warning: Winner '{winner}' does not match player/opponent in last row.")
            return last_row
    else:
        print(
            "Warning: No score columns found. Expected player_score/opponent_score "
            f"or '{winner_score_col}'."
        )
        return last_row

    try:
        last_row[target_col] = float(last_row[target_col]) + 1
    except Exception:
        last_row[target_col] = 1.0

    return last_row


def process_badminton_data(input_source, output_csv_path=PROCESSED_CSV, output_db_path=PROCESSED_DB):
    """
    Processes raw badminton match data and saves it to CSV and SQLite.
    
    Args:
        input_source: File path (str) or DataFrame containing the raw data.
        output_csv_path: Path to save the processed CSV.
        output_db_path: Path to save the processed SQLite database.
        
    Returns:
        pd.DataFrame: The processed DataFrame.
    """
    
    ensure_runtime_dirs()
    output_csv_path = Path(output_csv_path)
    output_db_path = Path(output_db_path)

    # 1. Load Data
    if isinstance(input_source, pd.DataFrame):
        df = input_source.copy()
    else:
        # Assume it's a file path or file-like object (e.g. Streamlit UploadedFile)
        try:
            df = pd.read_csv(input_source)
        except Exception as e:
             raise ValueError(f"Input source must be a file path, file-like object, or DataFrame. Error: {e}")

    _validate_required_columns(df)

    print("🚀 開始處理資料...")

    # Step 1. 移除 type 為 "接不到" 的列
    initial_len = len(df)
    df = df[df['type'] != '接不到']
    print(f"✅ 已移除 '接不到' 的資料 (移除 {initial_len - len(df)} 筆)")

    # 建立遮罩處理 getpoint_player
    # 邏輯: 只有每個 match/set/rally 的最後一球才應該有 getpoint_player，其餘設為 NaN
    mask_not_last_in_rally = df.duplicated(subset=['match_id', 'set', 'rally_id'], keep='last')
    df.loc[mask_not_last_in_rally, 'getpoint_player'] = np.nan
    print("✅ 'getpoint_player' 處理完畢。")

    # Step 2. 若 lose_reason 或 win_reason 包含「對手」則改為 NaN
    for col in ['lose_reason', 'win_reason']:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: np.nan if isinstance(x, str) and "對手" in x else x)

    # Step 3. 每場比賽的每個 set 最後插入一筆新資料，並新增 opponent 欄位
    # ----------------------------------------------------
    dfs_to_concat = []

    # 分組：每場比賽 + 該比賽的每個 set
    for (match_id, set_id), group in df.groupby(['match_id', 'set'], sort=False):
        group = group.copy()

        # --- 處理 opponent 欄位 ---
        players = group['player'].dropna().unique()
        if len(players) == 2:
            p1, p2 = players[0], players[1]
            opponent_map = {p1: p2, p2: p1}
            group['opponent'] = group['player'].map(opponent_map)
        else:
            group['opponent'] = np.nan
        
        # 加入原始資料
        dfs_to_concat.append(group)

        # 處理最後一筆 & 加分
        try:
            last_row = group.iloc[-1].copy()
            winner = last_row.get('getpoint_player')
            
            if pd.notna(winner):
                last_row = _increment_score(last_row, winner)
                dfs_to_concat.append(pd.DataFrame([last_row]))
        
        except Exception as e:
            print(f"Error processing last row: {e}")
            pass

    # 4. 最後一次合併所有資料
    new_df = pd.concat(dfs_to_concat, ignore_index=True)
    
    if 'score_status' in new_df.columns:
        new_df = new_df.drop(columns=['score_status'])
        print("✅ 已成功刪除 'score_status' 欄位。")
        
    # 輸出 CSV
    output_csv_path.parent.mkdir(parents=True, exist_ok=True)
    new_df.to_csv(output_csv_path, index=False)
    print(f"✅ 已完成：資料處理並儲存至 {output_csv_path}")
    
    # 輸出 SQLite
    try:
        output_db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(output_db_path)
        table_name = "match_data"
        new_df.to_sql(table_name, conn, if_exists="replace", index=False)
        conn.close()
        print(f"✅ 已將資料匯入 SQLite 資料庫 {output_db_path}")
    except Exception as e:
        print(f"⚠️ SQLite 匯入失敗: {e}")

    return new_df

if __name__ == "__main__":
    # 測試用：直接執行此檔案會嘗試處理 data/raw/all_dataset.csv
    if RAW_DATA_CSV.exists():
        process_badminton_data(RAW_DATA_CSV)
    else:
        print(f"{RAW_DATA_CSV} not found for testing.")
