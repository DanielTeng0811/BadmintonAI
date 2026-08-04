---
title: BadmintonAI
emoji: 🏸
colorFrom: red
colorTo: blue
sdk: docker
sdk_version: 1.32.0
app_file: front_page.py
pinned: false
---

# BadmintonAI

以自然語言查詢羽球逐拍資料，產生統計、圖表與戰術洞察；專案也包含一套可重現的 LLM 評測流程。

## 兩個主要入口

- **互動分析 App**：`front_page.py` 是 Streamlit 入口，供使用者提問、上傳資料並下載分析報告。
- **LLM 評測**：`LLM_as_a_Judge/LLM_as_a_Judge.py` 用於比較不同 prompt／模式的產出與 Judge 結果。

## 快速開始

建議使用 Python 3.10 以上，從專案根目錄執行：

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

建立不納入版本控制的 `.env`：

```env
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
GEMINI_API_KEY=...
APP_PASSWORD=...
```

依使用的模型供應商設定對應的 API key 即可。啟動 App：

```bash
streamlit run front_page.py
```

## 開發與測試

```bash
pip install -r requirements-dev.txt
python -m pytest
```

評測程式會依 `LLM_as_a_Judge/LLM_as_a_Judge.py` 末端的設定執行。它可能呼叫外部模型並產生成本，因此請先確認題目、模型、模式與 `ONLY_GENERATION` 等選項，再手動執行：

```bash
python LLM_as_a_Judge/LLM_as_a_Judge.py
```

## 專案地圖

```text
BadmintonAI/
├── front_page.py                 # Streamlit 互動式分析介面
├── config/                       # Prompt 與應用設定
├── utils/                        # 資料載入、資料處理、LLM client、分析流程
├── data/
│   ├── raw/                      # 原始逐拍資料
│   ├── processed/                # App 使用的 CSV / SQLite 資料
│   └── metadata/                 # 欄位與場地定義
├── LLM_as_a_Judge/               # 評測核心、模式設定與已保留的評測輸出
├── evaluation/questions/         # 評測題庫
├── notebooks/                    # 手動探索與產生的 notebook
├── scripts/                      # 批次處理、資料庫與輔助工具
├── tests/                        # 自動化測試
└── docs/                         # 文件、部署說明與研究紀錄
```

完整的目錄責任、資料處理規則與協作方式請見 [專案結構說明](docs/PROJECT_STRUCTURE.md)。

## 資料與評測輸出

- `data/processed/` 的資料庫與 CSV 是 App 執行所需的版本化資料。
- `LLM_as_a_Judge/result_*/` 保留可供團隊檢視的完整評測輸出，包括 notebook、CSV、圖表、`summary.txt` 與 `run_manifest.json`。
- 新增評測結果時，請依既有的 `result_<model>/<run_name>/` 結構存放；不要覆寫既有 run，讓結果可以追溯。

## 支援功能

- 中文自然語言資料查詢與程式碼生成
- 資料上傳、清理與 SQLite 更新
- 澄清問題、程式執行修正、邏輯檢查與戰術洞察
- Baseline 與完整方法的 LLM 評測比較

## 文件

- [專案結構說明](docs/PROJECT_STRUCTURE.md)
- [LLM 評測目錄導覽](LLM_as_a_Judge/README.md)
- [部署說明](docs/DEPLOYMENT.md)
- [評測題目重分組](docs/evaluation_question_regrouped_scheme.md)
