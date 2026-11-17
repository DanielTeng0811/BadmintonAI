# Hugging Face 授權資料存取

目標是原版 BadmintonGPT 使用的 `howard9199/Badminton`。帳號需獲資料集核准，並在本機根目錄 `.env` 設定該帳號的讀取 token：

```dotenv
HF_TOKEN=<自己的讀取 token>
```

token 不要放在命令列參數或 Git。既有模型金鑰、模型選擇與實驗室其他服務設定不變。資料集授權只代表 HF 資料存取，不代表取得 badminton-analyze、reels 等獨立服務的權限。

## 同步

```bash
# 解析目前 revision，只快取不超過 8 MiB 的 CSV，不改正式 DB。
python3 scripts/badminton_gpt.py sync-hf

# 用最近完整快取離線建庫、驗證及啟用；沒有快取時先同步。
python3 scripts/badminton_gpt.py ingest
python3 scripts/badminton_gpt.py build
python3 scripts/badminton_gpt.py up
python3 scripts/badminton_gpt.py verify
python3 scripts/badminton_gpt.py preview

# 重現本次固定資料版本。
python3 scripts/badminton_gpt.py ingest --revision 0d203a44c500932ef54c212046f7b7c63c7f5c62
```

主機只用 Python 標準函式庫，不需要模型 API、額外的 Hugging Face CLI 或 GPU。

- 所有資料放在 `.runtime/badminton-gpt/huggingface/<revision>/`；Git 忽略整個快取。
- `inventory.json` 保存同一 revision 的完整檔案清單，包含遠端影片 metadata。
- `manifest.json` 記錄已下載 CSV 的 SHA-256、大小與是否使用快取。
- `current.json` 指向最近一次完整同步成功的快照。
- 下載會驗證 Hugging Face 的 Git blob／LFS oid，已存在且通過校驗的檔案可重用；損壞快取會重新下載。
- 命令只下載 CSV。影片清單不等於本機影片，不把遠端檔案存在直接標記為本機可播放。
- 預設每個 CSV 上限 8 MiB，回應本體也設大小上限；超過者列入 `skipped_large_csvs`，不下載。若有 CSV 被跳過，拒絕切換正式 DB，避免把不完整來源當完整資料集。已驗證快照每個 CSV 最大僅 126,523 bytes，915 檔全部符合上限。
- Authorization 只發給 HTTPS Hugging Face；重新導向到下載 CDN 時移除該 header。日誌不輸出 token、授權 headers 或帶簽章的下載 URL。

## 目前核對結果

2026-10-30 已以授權憑證驗證並快取資料集 revision `0d203a44c500932ef54c212046f7b7c63c7f5c62`：

| 項目 | 實際清單／內容 |
| --- | ---: |
| CSV | 915 檔，19,125,593 bytes |
| 資料夾目錄 | 232 |
| 含逐拍標註的資料夾 | 192 |
| `label/*.csv` | 469 檔、164,219 列原始標註 |
| `RallySeg.csv` | 224 檔、18,975 列原始片段紀錄 |
| `match_info.csv` | 50 檔 |
| 遠端 MP4 清單 | 16,413 檔，66,298,041,614 bytes |
| 已下載影片 | 0 |

這些是該快照的原始統計，未宣稱已完成跨來源去重、全部屬正式比賽，或代表上游最新版。232 個目錄也包含練習等資料，不能直接稱為 232 場正式比賽。

本機核對摘要在 `.runtime/badminton-gpt/huggingface/profile.json`。與現有兩包資料有 38 個正規化同名候選；已比對的 66 個逐局檔中，有一個標註列數不同。同名或欄位相似不能直接當成完全相同的資料版本。

## 已啟用資料庫

`scripts/import_huggingface_data.py` 在固定上游 DB image 內直接使用原版 `LocalSource`、`ShotLabel`、`parse_rally_seg`、`derive_ab`、`insert_match_row` 與 `ingest_match`，沒有重寫另一套主要解析邏輯。建庫容器無網路、唯讀根目錄，僅掛載指定快照與暫存輸出，不掛入 `.env`。

| 匯入結果 | 數量 |
| --- | ---: |
| 正規化目錄後的紀錄 | 231（226 正式、5 練習） |
| 含逐拍標註的正式比賽 | 188 |
| `shots` | 161,138 |
| `rallies` | 18,524 |
| 遠端回合影片清單 | 16,382 |
| 清單有對應影片的回合 | 16,038 |
| 遠端全場影片清單 | 31 |
| YouTube 來源連結 | 50 |
| 已下載影片 | 0 |

與原版一致：正規化同名目錄只選 label CSV 最多的一份，保留全部候選路徑；練習保留在目錄但不匯入其拍數／回合；只解析第 1～3 局。缺少標註的目錄仍存在，不能把所有目錄筆數當成有拍數的比賽數。

A/B 優先採用 `match_info.csv`，其次採原版資料夾／RallySeg 規則；不能把 A 一律視為勝者。12 筆目錄紀錄（含 5 筆練習）沒有可用姓名映射。未知年份改存 NULL，避免沿用原版的 2022 fallback。419 列球種亂碼依原版清理為「未知球種」，原文保存在來源 JSON。原版可解析列沒有被丟棄。

六份 `set4.csv` 共 86 列另存 `excluded_annotations` 並標記 `unsupported_set_number`，待確認資料意義，不加入 `shots`。HF 完整原始 CSV 快取仍保留。此流程重現原版的目錄選擇與拍數解析，未自行做跨資料集的逐拍合併。

### 額外追溯表

| 表 | 用途 |
| --- | --- |
| `hf_dataset`、`hf_source_files` | repo、完整 revision、CSV 大小與 SHA-256 |
| `match_sources` | 選用目錄、同名候選、A/B 依據及原始 match_info |
| `shot_sources` | 每筆 `shot_id` 的 CSV 路徑、行號、影格與完整原始 JSON |
| `rally_sources` | 匯入來源的原始 RallySeg 列 |
| `rejected_annotations`、`excluded_annotations`、`data_quality_issues` | 解析失敗、未支援局數與未知映射 |
| `remote_videos` | 回合影片路徑、大小、固定 revision URL、`availability='listed'`、`local_downloaded=0` |
| `remote_match_videos` | 全場影片清單；不猜測與目錄的對應 |

`rallies.remote_video_available=1` 只表示同一目錄／回合 ID 在遠端清單中有對應；`has_video=0`、`video_filename=NULL` 表示沒有本機檔案。遠端 HF URL 仍需要讀取者自己的授權；URL 不包含 token，程式不代理下載影片。

```sql
SELECT year,COUNT(*) AS n FROM matches WHERE is_practice=0 GROUP BY year ORDER BY year;
```

```sql
SELECT player_a,player_b FROM matches WHERE name='2025game1';
```

```sql
SELECT player,COUNT(*) AS n FROM shots WHERE match_name='2025game1' GROUP BY player;
```

## 驗證、備份與回復

`scripts/huggingface_oracle.py` 先獨立讀取已校驗 CSV，產生 17 題答案與本機 oracle；不從建好的正式 DB 反推答案。正式建庫逐題比對 oracle，檢查 integrity 和 foreign keys，通過後才備份並替換輸出。`verify` 再經真實 MCP 比對答案、確認唯讀／列數限制及每筆拍數的來源追溯，另驅動真實 Agent → skill → MCP → sandbox Python → visualizer 流程。不呼叫 Luna，沒有模型能力分數。

下載器的憑證、路徑、校驗與大小限制納入主線 `pytest`。另可用合成資料，在已建置 DB image 內執行原版解析器整合測試（不需 HF token）：

```bash
docker run --rm --network none --read-only --tmpfs /tmp \
  -v "$PWD/scripts:/repo/scripts:ro" \
  -v "$PWD/tests/integration/hf_ingest_check.py:/check.py:ro" \
  badmintonai-db:7cccbb1 python3 /check.py
```

切換前的整個 data 目錄保存在 `.runtime/badminton-gpt/backups/before-source-switch-<時間>-<ID>/`。本次原 94 場資料的備份是 `before-source-switch-20261030T152618Z-ac1089`。帳號與對話使用原 Docker volumes，資料來源切換不清除它們，既有對話圖表仍反映當時的來源。

可明確切回不需 HF 授權的兩包 ZIP 來源：

```bash
python3 scripts/badminton_gpt.py ingest --source shuttleset
python3 scripts/badminton_gpt.py build
python3 scripts/badminton_gpt.py up
python3 scripts/badminton_gpt.py verify
```

來源快取、HF 題目／答案與驗證報告維持本機 `.runtime/` 保存；不發布 gated 原始資料或憑證。Git 只保存程式與使用說明。

2026-10-30 驗收：主線單元測試 30 項、原版解析器合成資料整合測試 2 項、真實 MCP／Agent／Python／圖表流程 25／25、帳號隔離 61／61 全部通過，模型請求為 0。已將圖表中的空白球員標為「未標註」，保留在比例分母，並實際渲染確認三個分類皆完整顯示；admin 專屬離線預覽已更新。三個正式服務均健康。
