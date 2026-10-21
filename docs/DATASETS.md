# ShuttleSet 資料庫

正式資料庫由兩個原始 ZIP 建立，檔案保留在 [data/sources/](../data/sources/README.md)。本機輸出為 `.runtime/badminton-gpt/data/badminton.db`，不修改舊的 `data/processed/processed_new_3.db`。

## 本次實際內容

| 來源 | 原始比賽數 | 逐局 CSV | 原始標註列 | 影片連結 |
| --- | ---: | ---: | ---: | ---: |
| ShuttleSet | 44 | 104 | 36,484 | 43 |
| ShuttleSet22 | 58 | 140 | 52,356 | 0 |
| 合併去重後 | 94 | 223 個唯一比賽／局組合 | 81,938 | 43 |

去重後有 7,888 個 `(match_name,set_no,rally)` 回合。依年分為 2018：3 場、2019：8 場、2020：9 場、2021：24 場、2022：50 場。統計來自壓縮檔實際內容；README 的論文統計不直接作為資料列數答案。

## 去重與資料品質

- 比賽識別使用日期、正規化球員姓名組合、賽事與輪次；同名資料夾若出現衝突則中止匯入。不能只靠球員配對或來源 match ID 合併。
- 兩份來源的 8 場、21 個逐局 CSV 在統一整數／小數及時間格式後，內容一致。逐列正規化完整原始欄位，再連同比賽及局計算 fingerprint；跨來源重複列不再次加入 `shots`。
- 一筆完全相同的來源內重複也合併；總共移除 6,902 筆來源重複，88,840 列來源仍完整保存在 `shot_sources`。
- Anthony Ginting／Rasmus Gemke 2021 泰國公開賽第 3 局，回合 25 的拍號 1 有兩個不同影格，兩筆皆保留，以 `shot_id` 區分並記錄 `repeated_shot_number`。不擅自修正拍號或刪除未知／有 flaw 的標註。
- 原始空值維持 NULL，球種與得失分原因保持原文；各種分析應明示是否排除 flaw 或未知球種。
- A 是該場勝者、B 是敗者；由 `matches.player_a/player_b` 查姓名。`getpoint_player` 是該回合得分方，不一定是末拍擊球者。`win_reason` 非空也包含對手失誤；若問「標註落地致勝」需明確篩選 `win_reason='落地致勝'`。

## 表與欄位

### 與原版 BadmintonGPT 的對接

```text
ShuttleSet.zip + ShuttleSet22.zip
  → 本機匯入與去重 → SQLite matches／rallies／shots
  → 原版 badminton-db MCP → nanobot 依 skill 查詢 → Python 計算與 visualizer 圖表
```

沿用固定上游版本的 `mcps/badminton-db/server.py`，Agent 以原設定的 `streamableHttp` 連線至 `http://badminton-db:8801/mcp`，使用 `list_tables`、`describe_table`、`query` 三個工具。新增的是來源 ZIP 的轉換、去重與追溯層，原版 Agent loop、MCP 查詢介面及三張核心表的原有欄位保留。

正式 `matches` 的來源是 ShuttleSet 44 場，加上 ShuttleSet22 去除重疊後的 50 場。舊的五筆處理資料僅在歷史表保存；新 benchmark、首頁範例及資料查詢 skill 的範圍都以這兩包資料為準。

### Schema 擴充

| 表 | 用途 |
| --- | --- |
| `matches` | 去重正式比賽，沿用上游欄位，增加 `match_date`、`video_url` |
| `shots` | 去重逐拍標註，增加穩定的 `shot_id`，作為目前統計來源 |
| `rallies` | 依原始局／回合分組，保留標註影格範圍 |
| `shot_details` | 以 `shot_id` 連接影格、秒數、原始區域碼、擊球／落點與雙方位置座標、flaw |
| `datasets` | 原始 ZIP 的路徑、SHA-256 與內容筆數 |
| `match_sources`、`match_homographies` | 每份來源的比賽 metadata 與原始 homography 資訊 |
| `shot_sources` | 每一筆來源列、CSV 路徑、行號、原始 JSON；不可把此表筆數當去重拍數 |
| `match_links` | 原始影片 URL 與來源，availability 維持 `unverified` |
| `data_quality_issues` | 保留並說明原始異常 |
| `legacy_match_aliases` | 舊五筆處理資料對應正式完整比賽的證據 |
| `legacy_matches`、`legacy_shots`、`legacy_rallies` | 先前版本的 5 筆／5,204 拍／409 回合，供歷史結果重現 |

原始來源區域碼存於 `shot_details.source_hit_area/source_landing_area`；尚未驗證和上游 skill 的球場網格相同，所以 `shots.hit_area/landing_area` 暫留 NULL。座標是來源相機座標，不能直接當公尺。原始 hit_height、landing_height、其他欄位與字串格式可從 `shot_sources.raw_data` 追溯。

原始 `match.csv` 的 set、duration、downcourt 等欄位保留於 `match_sources.raw_metadata`。此 schema 保留上游三張表與 MCP 介面；額外表可經相同的 `list_tables`／`describe_table`／`query` 查詢。

## 影片

兩個壓縮檔都沒有影片。43 個 YouTube 網址原樣保留，尚未連線確認是否可播放，也沒有下載影片或呼叫實驗室服務。`rallies.has_video=0`、`video_filename=NULL`；時間／影格是已標註擊球位置，不能當作完成驗證的剪輯邊界。

## 舊資料遷移

舊資料的 5 筆紀錄，全部不同的 `(set,frame,player)` 都能在唯一一場來源比賽中找到。歷史別名分別對應 Momota／Chou 的 2019 福州決賽、2019 韓國決賽、2018 福州決賽、2018 丹麥決賽、2018 馬來西亞八強。

舊處理資料有過濾及座標轉換，因此不將其逐拍列和原始 CSV 混在一起，也不把舊子集拍數描述成完整比賽拍數。歷史資料與對話保留，正式總數使用新表。接入前本機 DB 備份保存在 `.runtime/badminton-gpt/backups/pre-shuttleset/`。

## 重建與驗證

```bash
python3 scripts/badminton_gpt.py ingest
python3 scripts/badminton_gpt.py build
python3 scripts/badminton_gpt.py up
python3 scripts/badminton_gpt.py verify
python3 scripts/badminton_gpt.py preview
```

`ingest` 先重建獨立 CSV oracle 並比對凍結答案，再匯入正式 DB；不會自行更新凍結答案。匯入在暫存 DB 完成，檢查 integrity／foreign keys 後才原子取代輸出。測試包含中途失敗仍保留原 DB，以及重複匯入後數量一致。

Git 保存兩個來源 ZIP、SHA-256、匯入器、凍結題目與驗證紀錄；約 145 MiB 的本機 SQLite 產物留在被忽略的 `.runtime/`，可用上述指令重建。帳號、對話、金鑰及本機測試憑證不隨資料更新提交。

來源資料若有意更新，應先人工檢視差異，再用 `python3 scripts/create_shuttleset_benchmark.py --refresh` 重新凍結基準；不能為了通過驗證而修改 expected。

## 查詢範例

MCP 每次只接受一個 SELECT，最多回傳 200 列。應先找出 `matches.name` 再限定單場。以下每段分別執行：

```sql
SELECT year, COUNT(*) AS matches FROM matches GROUP BY year ORDER BY year;
```

```sql
SELECT name, player_a, player_b, match_date, video_url
FROM matches WHERE video_url IS NOT NULL ORDER BY match_date;
```

```sql
SELECT s.type, COUNT(*) AS n FROM shots s JOIN matches m ON m.name=s.match_name
WHERE m.year=2022 GROUP BY s.type ORDER BY n DESC;
```

```sql
SELECT legacy_name, match_name, matched_frame_player_keys, total_frame_player_keys
FROM legacy_match_aliases ORDER BY legacy_name;
```

查詢與圖表驗證使用獨立讀取 CSV 的 16 題 oracle，以及真實 Agent → skill → MCP → sandbox Python → visualizer 流程。固定步驟驗證不呼叫模型，不代表 Luna 回答品質已通過測試。

本次 [驗證紀錄](../benchmarks/badminton_gpt/shuttleset_baseline.json) 保存 24／24 項實際離線流程檢查、20 項主線測試，以及 61／61 項帳號隔離檢查。瀏覽器已確認新版資料的圖表能正常顯示；正式帳號資料庫未建立測試帳號。
