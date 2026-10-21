# 專案結構與協作規則

目前主線為 [BadmintonGPT 本機重現](BADMINTON_GPT_REPRODUCTION.md)。入口是 `scripts/badminton_gpt.py`，由 `compose.badminton-gpt.yml` 啟動固定版本上游的 nanobot WebUI 與資料庫 MCP。`front_page.py` 和既有評測流程保留為舊版研究材料。

## 目錄責任

| 目錄／檔案 | 用途 | 放入原則 |
| --- | --- | --- |
| `scripts/badminton_gpt.py` | BadmintonGPT 主入口 | 統一管理建置、資料匯入、啟動與驗證；不要繞回舊版分析流程。 |
| `vendor/badmintonGPT/` | 固定版本的上游 submodule | 保留上游原始碼；本機調整由 build context overlay 套用。 |
| `benchmarks/badminton_gpt/` | 自有 benchmark 與凍結答案 | 記錄來源 hash；答案須來自獨立來源查詢，不由模型生成。 |
| `.runtime/badminton-gpt/` | 可重建資料與本機執行結果 | 不納入版本控制，不存金鑰；每次 benchmark 使用獨立 run。 |
| `front_page.py` | 舊版 Streamlit 入口 | 保留供研究追溯，新開發以 BadmintonGPT 入口為主。 |
| `config/` | Prompt 與設定 | Prompt、模式無關設定集中於此；避免在 UI 或腳本內複製。 |
| `utils/` | 應用核心服務 | 資料載入、資料處理、模型 client、分析工作流與路徑設定。 |
| `data/raw/` | 原始資料 | 不修改來源內容；處理後資料另存。 |
| `data/processed/` | App 執行資料 | 版本化的 CSV／SQLite；名稱變更時，同步更新 `utils/paths.py`。 |
| `data/metadata/` | 資料字典 | 欄位定義、場地區域等可供程式與 prompt 共用的參考資料。 |
| `LLM_as_a_Judge/` | 評測核心與輸出 | 評測流程、模式設定、輸出合約與可追溯結果。 |
| `evaluation/questions/` | 結構化評測題庫 | 題目檔與題目分類的唯一來源。 |
| `notebooks/` | 探索與人工分析 | Notebook 不應成為 App 的唯一實作來源。 |
| `scripts/` | 可重複執行的工具 | 批次任務必須可從專案根目錄執行。 |
| `tests/` | 自動化測試 | 新增行為或修正 bug 時，優先新增相對應測試。 |
| `docs/` | 維護與研究文件 | 供協作者閱讀的架構、部署與研究決策。 |

## 評測輸出規則

評測輸出目前是團隊需要共同檢視的研究材料，因此保留在版本控制中。每次執行應建立獨立 run 目錄，建議包含：

```text
LLM_as_a_Judge/result_<model>/<run_name>/
├── run_manifest.json      # 模型、模式、題目與執行設定
├── summary.txt            # 供快速閱讀的摘要
├── eval_results.csv       # 逐題結果
├── stage_usage.csv        # 各階段用量／成本資料
├── eval_notebook.ipynb    # 可重現的完整輸出
└── plots/                 # 圖表輸出
```

不要修改完成的 run；如果要重跑，建立新的 `<run_name>`。研究結論可另外整理成 `docs/` 的 Markdown 文件，並連回對應 run 的 `run_manifest.json`。

## 分支規則

- `main`：可部署、可交付的穩定版本。
- `fix/report-bug-and-token`：目前整合最新評測與輸出模板工作的分支；合併到 `main` 前應先跑完整測試。
- `drawPic`：保留待檢視的資料／分析流程整理工作。
- 其他 2025 年實驗分支暫時保留，直到團隊確認其中沒有需要回收的內容。

新工作請使用描述目的的分支，例如 `feature/data-import`、`fix/evaluator-summary` 或 `docs/project-structure`。完成並驗證後再合併，避免長期分支累積。

## 修改前檢查

1. 確認變更屬於正確目錄，而不是直接寫入 UI 或 notebook。
2. 若修改資料路徑，同步更新 `utils/paths.py` 與相關測試。
3. 若修改評測模式或輸出格式，先檢查 `LLM_as_a_Judge/mode_config.py`、輸出合約與既有測試。
4. 執行 `python -m pytest`；涉及模型呼叫的評測需另外由人工確認成本與結果。
