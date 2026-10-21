# BadmintonGPT 本機重現

本專案以 [NYCU-ADSL/badmintonGPT](https://github.com/NYCU-ADSL/badmintonGPT) 的 `7cccbb18aba8bcfa096f22b923fb2aa16326e6ed` 為基準，透過 Git submodule 固定原始碼。沿用其客製 nanobot、WebUI、Agent loop、skill 載入方式、SQLite MCP 與圖表 renderer。舊版 Streamlit 流程和 LLM-as-a-Judge 結果集中保留於 [legacy/](../legacy/README.md)，不在新入口的執行路徑中。

## 重現範圍

| 元件 | 本機版本 |
| --- | --- |
| nanobot Agent / WebUI | 從固定上游程式建置 |
| skill → MCP → Python → 圖表 | 真實工具流程已納入離線驗證 |
| GPT Luna | 預設 `gpt-6-luna`，使用 Responses API；待新金鑰實測 |
| 資料庫 | 既有資料轉成相同 `matches` / `rallies` / `shots` schema |
| 本機登入、多使用者與對話隔離 | 已提供獨立登入服務，詳見 [本機帳號指南](LOCAL_ACCOUNTS.md) |
| Hugging Face 完整資料集 | 需要核准，未下載、未假裝重現其覆蓋率 |
| 遠端 advanced analysis / video retrieval / reels | 無權限，停用工具與 skills |
| Cloudflare Tunnel | 本機不需要；保留未來接入帳號服務的雲端部署方向，見 [雲端部署規劃](CLOUD_DEPLOYMENT.md)；尚未公開上線 |

目前的工作目標是可重建的本機基礎系統與自有 benchmark，不宣稱復現上游論文或完整系統的效能數字。

## 啟動與操作

從專案根目錄執行，主機只需 Docker Desktop、Compose 與 Python 3.10+；其餘套件在容器內：

```bash
git submodule update --init vendor/badmintonGPT
python3 scripts/badminton_gpt.py ingest
python3 scripts/badminton_gpt.py build
python3 scripts/badminton_gpt.py up
python3 scripts/badminton_gpt.py verify
python3 scripts/badminton_gpt.py preview
```

WebUI 為 <http://127.0.0.1:8765>。首次先設定 admin 密碼；側欄的「離線驗證預覽」僅 admin 可見，是固定步驟測試產生的真實數據圖表，沒有呼叫模型。首頁範例已改成目前可查的資料，並提醒先設定 Luna 金鑰。

```bash
python3 scripts/badminton_gpt.py status
python3 scripts/badminton_gpt.py logs
python3 scripts/badminton_gpt.py down
```

`down` 保留 Docker volume 中的對話。`up` 會重新套用設定並重建容器，不刪對話。`build` 從固定上游複製出忽略版本控制的 build context，只調整本機資料說明及首頁範例文字；上游 submodule 維持乾淨。修改本機範例或 skill overlay 後需重新 `build`、`up`。

預設連接埠可透過 `.env` 中的 `BADMINTONGPT_PORT`、`BADMINTONGPT_DB_PORT` 調整；主機端 MCP 為 `http://127.0.0.1:8801/mcp`，容器間仍使用原本的 `http://badminton-db:8801/mcp`。

## Luna 金鑰到位後

把以下欄位合併到根目錄既有 `.env`，保留其他設定：

```dotenv
OPENAI_API_KEY=你的新金鑰
NANOBOT_MODEL=gpt-6-luna
OPENAI_API_BASE=https://api.openai.com/v1
```

若帳號或實驗室代理提供不同的 Luna 模型 ID／API base，使用提供方實際值。程式不會自動換成另一個模型。官方 [GPT-6 Luna 文件](https://developers.openai.com/api/docs/models/gpt-6-luna) 建議工具呼叫使用 Responses API，因此本機設定明確使用 `apiType=responses`，不以 Chat Completions 自動降級。

```bash
python3 scripts/badminton_gpt.py up
python3 scripts/badminton_gpt.py benchmark --live
```

`--live` 才會產生模型 API 費用。尚未提供金鑰前不執行、不宣稱通過此測試。既有金鑰的模型可用性檢查曾對 `gpt-6-luna`、`gpt-5.6-luna` 回傳 404；不代表新金鑰一定有或沒有權限，仍需實測。

## 資料來源與轉換

唯一來源是版本化的 `data/processed/processed_new_3.db`，共 5,204 拍。匯入程式唯讀開啟來源，直接使用上游 DDL，先建立暫存 DB，通過 SQLite integrity / foreign-key 檢查後才取代輸出。

| 名稱 | 原始 match_id | 拍數 |
| --- | --- | ---: |
| legacy_match_1 | 1 | 1549 |
| legacy_match_3 | 3 | 805 |
| legacy_match_5 | 5 | 1073 |
| legacy_match_6 | 6 | 1029 |
| legacy_match_7 | 7 | 748 |

A = Kento MOMOTA，B = CHOU Tien Chen，以明確的 score 欄名建立穩定映射。保留原始球種、得失分原因、局、拍序和分數。409 個回合以 `(match_id, set, rally)` 區分，避免跨場或跨局混在一起。

限制必須隨分析保留：

- 原始紀錄不足以判定正式比賽名稱、賽事、日期或輪次，metadata 保留 NULL；五筆紀錄不等於已證實五場獨立正式比賽。
- 沒有影片，所以 `has_video=0`、`video_filename=NULL`；回合 ID 保留原始編號，不能交給 reels 當影片 ID。
- 原資料的場地區域編碼和上游 1–16 不同，`hit_area`／`landing_area` 留 NULL，不能假裝已完成對應。
- frame 範圍是該回合已標註拍的最小與最大 frame，不是可播放片段邊界。
- 不補推進階運動、球高、休息時間或遠端分析數據。

來源 SHA-256、匯入筆數、A/B 映射與限制記錄在 `.runtime/badminton-gpt/data/manifest.json`。該資料可作為初期開發集；未來應另取得有使用權的多球員、多賽事資料，按整場比賽切分開發／測試集，避免同一場回合洩漏到兩側。

## Benchmark 與驗證

2026-10-21 的本機驗證：18／18 項離線檢查通過，既有與新增回歸測試共 171 項通過。兩個容器皆 healthy，瀏覽器已確認本機首頁與 visualizer 圖表。完整結果保存在 [離線基準紀錄](../benchmarks/badminton_gpt/offline_baseline.json)；其中明確標示模型沒有執行。此紀錄描述當次版本，之後修改仍應重新執行驗證。

`benchmarks/badminton_gpt/cases.json` 包含 10 題與凍結答案，涵蓋資料範圍、全庫拍數、單筆過濾、A/B、球種、致勝球、局、回合、缺少影片與比例圖表。答案由**原始 DB 的獨立 SQL** 建立，不由匯入結果或模型生成。保留 `source_sql`、`target_sql`、來源 hash 和 expected rows。

`verify` 實際啟動 MCP Client 連線，檢查資料答案、唯讀限制、200-row 上限與缺少場地標籤。另用明確標示的 scripted provider 驅動真實 nanobot，依序讀 skill、查 MCP、在原本的 bubblewrap sandbox 執行 Python、產生 visualizer 圖表。這驗證接線與執行，不測模型推理品質。

`benchmark --live` 才用設定的 Luna 做相同問題，保存答案與完整工具 trace，檢查答案、資料庫工具與 skill 讀取；圖表題另檢查 Python 執行、visualise skill 和 visualizer 輸出。機械檢查不等於人工確認戰術推論或圖表的所有語意；目前題庫也不是上游的完整 benchmark。每次產生獨立 run，保存於 `.runtime/badminton-gpt/benchmark-runs/`，不覆寫已完成 run。

回歸測試：

```bash
uv run --with pytest --python 3.12 python -m pytest tests/test_badminton_gpt_reproduction.py -q
```

## 重現時修正的相容性

上游 DB Dockerfile 的 `mcp>=1.0` 現在會安裝 MCP v2，而原程式仍 import `mcp.server.fastmcp`，容器直接失敗。本機 DB image 固定 `mcp==1.26.0`。上游 DDL 以 `matches.name` 作外鍵但未宣告唯一；匯入時新增唯一索引，使 SQLite 能實際驗證關聯。

## 檔案位置

- `vendor/badmintonGPT/`：固定版本的上游 Git submodule。
- `compose.badminton-gpt.yml`：本機容器、連接埠、資料與設定掛載。
- `scripts/badminton_gpt.py`：setup / build / ingest / up / verify 等入口。
- `scripts/import_badminton_gpt_data.py`：原資料到上游 schema。
- `scripts/create_badminton_gpt_benchmark.py`：從來源凍結 oracle；已有檔案時拒絕覆寫。
- `scripts/badminton_gpt_benchmark.py`：MCP 驗證、Agent 接線測試與可選 live evaluation。
- `.runtime/badminton-gpt/`：可重建 DB、build context、驗證結果，全部忽略版本控制。

不要直接執行會輸出展開後金鑰的 `docker compose config`；如只需檢查設定，用 `config --quiet`。金鑰留在 `.env`，不寫入 manifest、benchmark 或報告。
