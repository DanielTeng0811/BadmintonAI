import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from typing import List, Optional, Union

def _validate_columns(df: pd.DataFrame, required_cols: List[str]):
    """內部輔助：驗證欄位是否存在"""
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"Expected pandas DataFrame, got {type(df)}")
    
    # 檢查是否為空
    if df.empty:
        # 允許空 DataFrame 通過，但發出警告或是直接 return (視函數邏輯而定)
        # 這裡僅驗證 Schema，所以只要 columns 在就好
        pass

    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}. 請確保傳入完整的 DataFrame。")

def get_shot_context(df: pd.DataFrame, shift_n: int = 1) -> pd.DataFrame:
    """
    獲取前後 N 拍的資訊 (已處理 groupby match/set/rally)。
    """
    # Defensive checks
    if not isinstance(shift_n, int):
        raise TypeError(f"shift_n must be an integer, got {type(shift_n)}. (e.g., Use 1 for prev shot, -1 for next shot)")
    
    _validate_columns(df, ['match_id', 'set', 'rally', 'ball_round'])
    
    if df.empty:
        return df # 若輸入為空，直接回傳空，避免後續 error

    # 確保按照比賽順序排序
    df_sorted = df.sort_values(by=['match_id', 'set', 'rally', 'ball_round'])
    
    shifted = df_sorted.groupby(['match_id', 'set', 'rally'])[df.columns].shift(shift_n)
    
    suffix = f"_prev{abs(shift_n)}" if shift_n > 0 else f"_next{abs(shift_n)}"
    shifted.columns = [f"{col}{suffix}" for col in shifted.columns]
    
    return shifted.loc[df.index]

def filter_active_win(df: pd.DataFrame) -> pd.DataFrame:
    """
    篩選「主動得分」的回合 (Active Win)。
    """
    _validate_columns(df, ['player', 'getpoint_player', 'rally', 'ball_round'])
    
    if df.empty:
        return df

    last_shots = df.sort_values('ball_round').groupby(['match_id', 'set', 'rally']).tail(1)
    
    # 避免 Comparison error 如果欄位型別不一致 (雖不常見)
    active_wins = last_shots[last_shots['player'] == last_shots['getpoint_player']].copy()
    
    return active_wins

def filter_player(df: pd.DataFrame, player_name: str) -> pd.DataFrame:
    """
    篩選特定球員擊球的紀錄。
    """
    if not isinstance(player_name, str):
        raise TypeError(f"player_name must be a string, got {type(player_name)}: {player_name}")

    _validate_columns(df, ['player'])
    
    # 加上 strip() 避免空白導致篩不到
    clean_name = player_name.strip()
    return df[df['player'] == clean_name].copy()

def merge_small_slices(series: Union[pd.Series, dict, list], threshold: float = 0.05, other_label: str = "其他 (Others)") -> pd.Series:
    """
    [視覺化輔助] 合併圓餅圖的小區塊。
    """
    # 容錯：支援 dict 或 list 轉 Series
    if isinstance(series, (dict, list)):
        series = pd.Series(series)
    elif not isinstance(series, pd.Series):
        raise TypeError(f"Expected pandas Series/dict/list, got {type(series)}")

    total = series.sum()
    if total == 0:
        return series
        
    probs = series / total
    mask = probs < threshold
    
    if not mask.any():
        return series
        
    main_series = series[~mask]
    small_sum = series[mask].sum()
    
    other = pd.Series([small_sum], index=[other_label])
    return pd.concat([main_series, other])

def classify_area(zone_id: Union[int, float, str]) -> str:
    """
    根據 Zone ID (1-32) 判斷場地大區域 (Category)。
    """
    # 容錯：處理字串型別的數字
    try:
        if pd.isna(zone_id) or str(zone_id).lower() == 'nan':
            return "Unknown"
        zid = int(float(zone_id)) # Handle "1.0" string or float
    except (ValueError, TypeError):
        return "Unknown" # 無法轉成數字則回傳 Unknown，不報錯 crash
    
    if 17 <= zid <= 24:
        return "前場"
    elif 5 <= zid <= 16:
        return "中場"
    elif 1 <= zid <= 4:
        return "後場"
    elif 25 <= zid <= 32:
        return "出界"
    else:
        return "Unknown"


def get_rally_flow(df: pd.DataFrame, match_id: Union[int, float], set_num: int, rally_id: int) -> pd.DataFrame:
    """
    [除錯用] 取得特定 Rally 的完整來回過程。
    """
    _validate_columns(df, ['match_id', 'set', 'rally', 'ball_round'])
    # 強制轉型避免 int vs float 比對失敗
    mask = (df['match_id'] == match_id) & (df['set'] == int(set_num)) & (df['rally'] == int(rally_id))
    return df[mask].sort_values('ball_round')

def get_win_loss_reason_counts(df: pd.DataFrame, player_name: str):
    """
    [分析輔助] 統計球員的得分與失分原因。
    """
    if df.empty:
        return pd.Series(), pd.Series()
        
    if not isinstance(player_name, str):
        raise TypeError(f"player_name must be a string, got {type(player_name)}")

    last_shots = df.sort_values('ball_round').groupby(['match_id', 'set', 'rally']).tail(1)
    
    points_won = last_shots[last_shots['getpoint_player'] == player_name]
    win_reasons = points_won['win_reason'].value_counts()
    
    points_lost = last_shots[last_shots['getpoint_player'] != player_name]
    lose_reasons = points_lost['lose_reason'].value_counts()
    
    return win_reasons, lose_reasons

def get_zones_by_area(area_name: Union[str, List[str]]) -> List[int]:
    """
    根據場地大區域名稱 (Front/Mid/Back/Out) 回傳對應的 Zone ID 列表。
    容錯處理：支援字串 (e.g. "前後場") 或 列表 (e.g. ["前場", "後場"])。
    
    Mapping:
    - Front (前場): 17-24
    - Mid (中場): 5-16
    - Back (後場): 1-4
    - Out (出界): 25-32
    """
    if not area_name:
        return []

    # 容錯：若 LLM 傳入 list，將其合併為字串處理
    if isinstance(area_name, list):
        area_name = "".join([str(x) for x in area_name])
    
    if not isinstance(area_name, str):
        # 拋出清楚的錯誤訊息供 AI 自行修正
        raise TypeError(f"get_zones_by_area expects a string or list of strings, but got {type(area_name).__name__}: {area_name}")

    area = area_name.lower()
    zones = []
    
    if "front" in area or "前" in area:
        zones.extend(list(range(17, 25)))
    if "mid" in area or "中" in area:
        zones.extend(list(range(5, 17)))
    if "back" in area or "後" in area:
        zones.extend(list(range(1, 5)))
    if "out" in area or "出" in area:
        zones.extend(list(range(25, 33)))
        
    return sorted(list(set(zones)))