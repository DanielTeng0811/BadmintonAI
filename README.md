# BadmintonAI

以 [NYCU-ADSL/BadmintonGPT](https://github.com/NYCU-ADSL/badmintonGPT) 為基礎的羽球資料分析系統，沿用其 nanobot、WebUI、skills 與 MCP 工具流程，加入不依賴實驗室權限的帳號與對話隔離。模型設定保留 GPT Luna。

目前提供可重建的本機版本、ShuttleSet 資料整合與離線 benchmark。原本的 Streamlit、多模型實驗及 LLM-as-a-Judge 已集中到 [legacy/](legacy/README.md)。

## 目前狀態

| 功能 | 狀態 |
| --- | --- |
| nanobot WebUI、skills、SQLite MCP、Python 計算與圖表 | 已完成本機接線與離線驗證 |
| 註冊、登入、登出、修改密碼與管理員停用帳號 | 已完成 |
| 多使用者對話、專案、側欄與附件隔離 | 已完成實際 HTTP／WebSocket 驗證 |
| GPT Luna 回答 | 設定保留；等待可用 API key 實測 |
| ShuttleSet + ShuttleSet22 | 已去重匯入，保留來源與影片連結 |
| 實驗室進階分析與影片服務 | 尚無權限，相關工具暫停啟用 |
| 公開雲端部署 | 保留 Cloudflare Tunnel 路線，尚未上線 |

## 快速啟動

主機需要 Git、Python 3.10 以上，以及已啟動的 Docker／Docker Compose v2。主服務依賴由 Docker 安裝，啟動時不需要安裝舊版 Streamlit 套件。

```bash
git clone --recurse-submodules https://github.com/DanielTeng0811/BadmintonAI.git
cd BadmintonAI
python3 scripts/badminton_gpt.py ingest
python3 scripts/badminton_gpt.py build
python3 scripts/badminton_gpt.py up
```

既有 checkout 先執行 `git submodule update --init vendor/badmintonGPT`。上游固定於 `7cccbb18aba8bcfa096f22b923fb2aa16326e6ed`，本地調整只套用到建置副本。

開啟 <http://127.0.0.1:8765>，第一次自行設定 `admin` 密碼。沒有預設密碼；其他使用者可從登入頁註冊一般帳號。帳號功能不需要模型 API key，詳細操作見 [帳號與隔離指南](docs/LOCAL_ACCOUNTS.md)。

### 設定 Luna

首次執行會建立被 Git 忽略的 `.env`。將 [.env.badminton-gpt.example](.env.badminton-gpt.example) 中需要的欄位合併到 `.env`，保留既有設定：

```dotenv
OPENAI_API_KEY=<填入自己的金鑰>
NANOBOT_MODEL=gpt-6-luna
OPENAI_API_BASE=https://api.openai.com/v1
```

模型 ID 與 API base 必須使用供應方實際提供的值；程式不會自動改用其他模型。設定後再執行 `python3 scripts/badminton_gpt.py up`。目前尚未驗證真實 Luna 回答。

## 驗證與日常操作

以下檢查不呼叫模型、不消耗 API token：

```bash
python3 scripts/badminton_gpt.py verify       # 資料、MCP、計算與圖表
python3 scripts/badminton_gpt.py verify-auth  # 一次性帳號的真實隔離檢查
python3 scripts/badminton_gpt.py preview      # admin 專屬離線圖表預覽
python3 scripts/badminton_gpt.py status
python3 scripts/badminton_gpt.py logs
python3 scripts/badminton_gpt.py down
```

帳號與對話保存在 Docker volumes；`down` 保留資料。API key、帳號資料庫與 `.runtime/` 不提交到 Git。離線預覽是固定步驟產生的真實資料結果，不能作為模型回答能力的證明。

有有效金鑰後，才執行付費模型 benchmark：

```bash
python3 scripts/badminton_gpt.py benchmark --live
```

開發者可另建 Python 環境，執行目前主線的離線單元測試：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest
```

舊版研究測試與依賴獨立保留於 `legacy/`，操作見 [舊版存檔指南](legacy/README.md)。

## 資料與限制

目前使用 `data/sources/ShuttleSet.zip` 與 `ShuttleSet22.zip`，去重後共 **94 場比賽、81,938 筆逐拍標註、7,888 回合**，涵蓋 2018–2022 年。賽事、日期、輪次與球員由原始 metadata 匯入；原始壓縮檔保留，建置資料庫另存於 `.runtime/`。

兩包重疊的 8 場比賽已合併，另移除一筆完全重複標註，共去除 6,902 筆重複來源列。拍號相同但影格不同的紀錄保留並標記。舊 5 筆處理資料另存於 `legacy_*` 表，以 `legacy_match_aliases` 對應正式比賽，不加入目前總數。

**43 個原始 YouTube 連結已保留，尚未驗證播放狀態；沒有本機影片或回合剪輯。** 原始座標、區域碼、影格與時間皆可追溯，尚未宣稱與上游球場網格一致。詳細 schema、去重規則、查詢與重建方式見 [資料集指南](docs/DATASETS.md)。

目前的 16 題 benchmark 由另一套 CSV 讀取程式獨立凍結答案，適用於本機驗證，尚不代表跨資料集的泛化能力。舊版題目與驗證紀錄保留供追溯。

## 部署方向

後續採用「自有 HTTPS 網域 → Cloudflare Tunnel → 帳號服務 → BadmintonGPT」，實際程式執行在雲端 VM 或有使用權限的校內主機。現有版本只開放 localhost；正式網域、HTTPS 與公開環境驗收仍待部署階段完成。

詳見 [雲端部署規劃](docs/CLOUD_DEPLOYMENT.md)。API key 和影片服務待權限到位後再接入。

## 專案結構與文件

```text
BadmintonAI/
├── compose.badminton-gpt.yml   # 本機服務入口
├── local_auth/                # 帳號與身分驗證代理
├── scripts/                   # 建置、匯入、操作與驗證工具
├── vendor/badmintonGPT/        # 固定版本上游 submodule
├── data/                      # 共用的原始研究資料與來源資料庫
├── benchmarks/badminton_gpt/   # 凍結題目與驗證紀錄
├── tests/                     # 目前主線測試
├── docs/                      # 重現、帳號、部署與維護文件
└── legacy/                    # 舊版程式、測試、評測結果與歷史文件
```

- [重現範圍與驗證方式](docs/BADMINTON_GPT_REPRODUCTION.md)
- [資料來源、去重與查詢](docs/DATASETS.md)
- [帳號、多使用者與對話隔離](docs/LOCAL_ACCOUNTS.md)
- [雲端與 Cloudflare 部署規劃](docs/CLOUD_DEPLOYMENT.md)
- [目錄責任與維護規則](docs/PROJECT_STRUCTURE.md)
- [舊版研究存檔與路徑對照](legacy/README.md)

本專案授權見 [LICENSE](LICENSE)；上游原始碼及其 vendored 元件依各自授權條款使用。
