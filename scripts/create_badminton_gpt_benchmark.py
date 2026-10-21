#!/usr/bin/env python3
"""Freeze a small oracle from the original source DB, independently of the importer."""
import hashlib
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/processed/processed_new_3.db"
OUTPUT = ROOT / "benchmarks/badminton_gpt/cases.json"


def create():
    if OUTPUT.exists():
        raise SystemExit(f"Oracle already exists: {OUTPUT}. Review changes before replacing it.")
    db = sqlite3.connect(f"file:{SOURCE}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    specs = [
        ("catalog", "目前資料庫有幾筆比賽紀錄？", "SELECT COUNT(DISTINCT match_id) AS n FROM match_data",
         "SELECT COUNT(*) AS n FROM matches"),
        ("total_shots", "所有紀錄共有幾拍？", "SELECT COUNT(*) AS n FROM match_data",
         "SELECT COUNT(*) AS n FROM shots"),
        ("match_scope", "legacy_match_1 共有幾拍？只查這筆紀錄。", "SELECT COUNT(*) AS n FROM match_data WHERE match_id=1",
         "SELECT COUNT(*) AS n FROM shots WHERE match_name='legacy_match_1'"),
        ("player_mapping", "legacy_match_1 兩位球員各打了幾拍？用 A/B 作為 player 欄位。",
         "SELECT CASE player WHEN 'Kento MOMOTA' THEN 'A' ELSE 'B' END AS player,COUNT(*) AS n FROM match_data WHERE match_id=1 GROUP BY player ORDER BY 1",
         "SELECT player,COUNT(*) AS n FROM shots WHERE match_name='legacy_match_1' GROUP BY player ORDER BY player"),
        ("shot_distribution", "legacy_match_3 各球種各有幾拍？依球種名稱排序。",
         "SELECT type,COUNT(*) AS n FROM match_data WHERE match_id=3 GROUP BY type ORDER BY type",
         "SELECT type,COUNT(*) AS n FROM shots WHERE match_name='legacy_match_3' GROUP BY type ORDER BY type"),
        ("winners", "legacy_match_5 兩位球員各有幾拍直接致勝球？用 A/B 作為 player 欄位。",
         "SELECT CASE player WHEN 'Kento MOMOTA' THEN 'A' ELSE 'B' END AS player,COUNT(*) AS n FROM match_data WHERE match_id=5 AND win_reason IS NOT NULL AND win_reason!='' GROUP BY player ORDER BY 1",
         "SELECT player,COUNT(*) AS n FROM shots WHERE match_name='legacy_match_5' AND win_reason IS NOT NULL GROUP BY player ORDER BY player"),
        ("set_scope", "legacy_match_6 每局各有幾拍？回傳 set_no 與 n。",
         'SELECT "set" AS set_no,COUNT(*) AS n FROM match_data WHERE match_id=6 GROUP BY "set" ORDER BY "set"',
         "SELECT set_no,COUNT(*) AS n FROM shots WHERE match_name='legacy_match_6' GROUP BY set_no ORDER BY set_no"),
        ("rally_count", "所有紀錄共有幾個回合？回合需區分 match、局與原始回合編號。",
         'SELECT COUNT(*) AS n FROM (SELECT match_id,"set",rally FROM match_data GROUP BY match_id,"set",rally)',
         "SELECT COUNT(*) AS n FROM rallies"),
        ("no_video", "資料庫有幾個可播放的回合影片？",
         "SELECT 0 AS n", "SELECT COUNT(*) AS n FROM rallies WHERE has_video=1"),
        ("chart", "計算 legacy_match_1 兩位球員出手佔全場的百分比，四捨五入到小數點兩位，並畫長條圖。rows 欄位為 player、n、pct，player 用 A/B。",
         "SELECT CASE player WHEN 'Kento MOMOTA' THEN 'A' ELSE 'B' END AS player,COUNT(*) AS n,ROUND(100.0*COUNT(*)/(SELECT COUNT(*) FROM match_data WHERE match_id=1),2) AS pct FROM match_data WHERE match_id=1 GROUP BY player ORDER BY 1",
         "SELECT player,COUNT(*) AS n,ROUND(100.0*COUNT(*)/(SELECT COUNT(*) FROM shots WHERE match_name='legacy_match_1'),2) AS pct FROM shots WHERE match_name='legacy_match_1' GROUP BY player ORDER BY player"),
    ]
    cases = [{"id": ident, "prompt": prompt, "source_sql": sql, "target_sql": target,
              "expected": [dict(r) for r in db.execute(sql)], "requires_chart": ident == "chart"}
             for ident, prompt, sql, target in specs]
    db.close()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps({
        "dataset": "badmintonai_processed_new_3", "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "scope": "local development benchmark; not a held-out generalization evaluation",
        "cases": cases,
    }, ensure_ascii=False, indent=2) + "\n")
    print(f"Frozen {len(cases)} cases: {OUTPUT}")


if __name__ == "__main__":
    create()
