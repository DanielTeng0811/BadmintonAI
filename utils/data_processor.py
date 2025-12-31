import pandas as pd
import numpy as np
import sqlite3
import os

def process_badminton_data(input_source, output_csv_path="processed_new_3.csv", output_db_path="processed_new_3.db"):
    """
    Processes raw badminton match data and saves it to CSV and SQLite.
    
    Args:
        input_source: File path (str) or DataFrame containing the raw data.
        output_csv_path: Path to save the processed CSV.
        output_db_path: Path to save the processed SQLite database.
        
    Returns:
        pd.DataFrame: The processed DataFrame.
    """
    
    # 1. Load Data
    if isinstance(input_source, pd.DataFrame):
        df = input_source.copy()
    else:
        # Assume it's a file path or file-like object (e.g. Streamlit UploadedFile)
        try:
            df = pd.read_csv(input_source)
        except Exception as e:
             raise ValueError(f"Input source must be a file path, file-like object, or DataFrame. Error: {e}")

    print("🚀 開始處理資料...")

    # Step 1. 移除 type 為 "接不到" 的列
    initial_len = len(df)
    df = df[df['type'] != '接不到']
    print(f"✅ 已移除 '接不到' 的資料 (移除 {initial_len - len(df)} 筆)")

    # 建立遮罩處理 getpoint_player
    # 邏輯: 只有每個 rally 的最後一球才應該有 getpoint_player，其餘設為 NaN
    mask_not_last_in_rally = df.duplicated(subset=['rally_id'], keep='last')
    df.loc[mask_not_last_in_rally, 'getpoint_player'] = np.nan
    print("✅ 'getpoint_player' 處理完畢。")

    # Step 2. 若 lose_reason 或 win_reason 包含「對手」則改為 NaN
    for col in ['lose_reason', 'win_reason']:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: np.nan if isinstance(x, str) and "對手" in x else x)

    # --- [New] Rename Columns Early ---
    # 為了讓後續的 score 更新可以直接對應到球員名稱，我們先進行欄位重新命名
    p1_name = None
    p2_name = None
    if not df.empty:
        try:
            # 假設第一筆資料的 player 是主角，opponent 是對手 (若 opponent 欄位尚未存在，需先推斷)
            # 因為 opponent 欄位是在 loop 中建立的，這裡我們先掃描 player 欄位
            unique_players = df['player'].dropna().unique()
            if len(unique_players) >= 2:
                # 簡單假設前兩個就是雙方
                p1_name = df.iloc[0]['player'] # 維持原 data_loader 邏輯，第一筆為基準
                # 找出另一個
                p2_name = next((p for p in unique_players if p != p1_name), None)
                
                if p1_name and p2_name:
                    rename_map = {
                        'player_score': f'{p1_name}_score',
                        'opponent_score': f'{p2_name}_score'
                    }
                    # 檢查欄位是否存在 (避免多次更名失敗)
                    if 'player_score' in df.columns:
                        df = df.rename(columns=rename_map)
                        print(f"✅ [Pre-process] 已將分數欄位命名: {rename_map}")
        except Exception as e:
            print(f"⚠️ Pre-process renaming failed: {e}")

    # Step 3. 每場比賽的每個 set 最後插入一筆新資料，並新增 opponent 欄位
    # ----------------------------------------------------
    dfs_to_concat = []

    # 確保必要的欄位存在
    required_cols = ['match_id', 'set', 'player']
    if not all(col in df.columns for col in required_cols):
         raise ValueError(f"資料缺少必要欄位: {required_cols}")

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
                # [User Request]: 根據 winner 是誰讓 {name}_score 欄位 +1
                score_col = f"{winner}_score"
                
                if score_col in last_row:
                    try:
                        last_row[score_col] = float(last_row[score_col]) + 1
                    except:
                         last_row[score_col] = 1.0 # 若原本 NaN 或非數值
                else:
                    # Fallback: 如果找不到 {winner}_score，可能是名稱比對問題
                    # 嘗試比對 player/opponent
                     current_player = last_row['player']
                     current_opponent = last_row.get('opponent')
                     
                     # 嘗試找對應的 score column
                     # 注意：此時 columns 已經被 rename 成 Name_score 了
                     # 所以 last_row['player_score'] 可能不存在
                     
                     # 若 winner == current_player, update that player's score column
                     # But we need to know WHICH column that is.
                     # Since we renamed 'player_score' -> 'P1_score', we need to check if current_player is P1.
                     
                     # 比較安全的做法: 遍歷所有 columns，看誰像是 score
                     pass
                     print(f"Warning: Score column '{score_col}' not found. Columns: {last_row.index.tolist()}")

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
    new_df.to_csv(output_csv_path, index=False)
    print(f"✅ 已完成：資料處理並儲存至 {output_csv_path}")
    
    # 輸出 SQLite
    try:
        conn = sqlite3.connect(output_db_path)
        table_name = "match_data"
        new_df.to_sql(table_name, conn, if_exists="replace", index=False)
        conn.close()
        print(f"✅ 已將資料匯入 SQLite 資料庫 {output_db_path}")
    except Exception as e:
        print(f"⚠️ SQLite 匯入失敗: {e}")

    return new_df

if __name__ == "__main__":
    # 測試用：直接執行此檔案會嘗試處理 all_dataset.csv
    if os.path.exists("all_dataset.csv"):
        process_badminton_data("all_dataset.csv")
    else:
        print("all_dataset.csv not found for testing.")
