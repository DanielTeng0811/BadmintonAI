# LLM 評測目錄導覽

這個目錄包含兩種不同性質的內容：**可執行的評測程式**與**已完成的研究輸出**。兩者都需要保留，但閱讀或修改時應依用途區分。

## 程式與設定

| 檔案／目錄 | 用途 |
| --- | --- |
| `LLM_as_a_Judge.py` | 評測主流程與可直接執行的入口。執行前務必確認檔案底部的模型、題目與模式設定。 |
| `mode_config.py` | 集中定義 baseline、正式方法與隔離 `test` mode。 |
| `judge_prompt.py` | Judge 使用的 prompt。 |
| `evaluation_records.py` | 逐題與各階段的評測紀錄資料模型。 |
| `output_contract.py` | 評測輸出的格式驗證。 |
| `validation_sets.py` | 既定的題目子集。 |
| `test_output_adapter.py` | 只在隔離 `test` mode 使用的輸出轉接層。 |
| `test_output_runtime/` | 隔離模板的 payload、rendering 與範例產生器。 |

## 輸入資料

- `評估問題_new.txt`：目前評測入口使用的題目檔。
- `example_new.ipynb`：目前評測入口使用的參考範例。
- 舊版 `評估問題.txt` 與 `example.ipynb`：保留供比較，除非更新執行設定，否則不會被主流程讀取。

## 評測結果

以下目錄是研究記錄，不是可任意清除的暫存檔；每個 run 都應視為不可變結果：

```text
result_<model>/
├── <run_name>/
│   ├── run_manifest.json   # 執行設定與可追溯資訊
│   ├── summary.txt         # 摘要
│   ├── eval_results.csv    # 逐題結果
│   ├── stage_usage.csv     # token／成本與步驟記錄
│   ├── eval_notebook.ipynb # 完整輸出
│   └── plots/              # 產生的圖表
└── <run_name>.md           # 該 run 的閱讀摘要（如有）
```

目前保留的模型結果：

- `result_gpt4o/`
- `result_claude-sonnet4.6/`
- `result_gpt5.6-luna/`

新增執行時請建立新的 `<run_name>`，不要覆寫既有目錄；跨 run 的比較結論請寫成 Markdown，並註明使用的 `run_manifest.json`。

## 修改前檢查

1. 修改 mode 或 prompt 前，先閱讀 `mode_config.py` 與相關的 `tests/test_evaluator_modes.py`。
2. 修改輸出格式前，檢查 `output_contract.py`、`test_output_adapter.py` 與對應的 output tests。
3. 主流程會發出模型請求；不要把它當作一般單元測試執行。
4. 程式變更後從專案根目錄執行 `python -m pytest`。
