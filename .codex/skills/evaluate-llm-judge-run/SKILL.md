---
name: evaluate-llm-judge-run
description: 評估 BadmintonAI 的 LLM-as-a-Judge 已完成 run。當使用者要求分析、逐題檢查、人工複核、判定正確性、統計或比較 `LLM_as_a_Judge/eval_results/` 內的指定 run 的結果時使用；會依 `example_new.ipynb` 的可接受範例審核、更新該 run 的 summary.txt，並在 run 資料夾外建立同名 Markdown 統整報告。
---

# BadmintonAI Run 評估

只審核指定 run；除非使用者明確要求比較，否則不得混入其他 run 的資料或先前結論。

## 流程

1. 讀取 run 的 `summary.txt`、`eval_notebook.ipynb` 與可用的 `eval_results.csv`。
2. 執行 `python -X utf8 scripts/inspect_run.py <run_dir> --json`。單題程式使用 `--question <id> --show-code` 讀取。
3. 讀取 `references/review-standard.md`，並比對 `LLM_as_a_Judge/example_new.ipynb` 的同題所有範例。
4. 逐題人工判定 `正確` 或 `錯誤`，檢查主體、粒度、回合邊界、得失分、比例與產出。
5. 完成所有題目後，使用 `scripts/finalize_review.py` 寫入結果。

## 判定原則

- `example_new.ipynb` 的多個版本都是可接受參考，不可用單一範例限制判定。
- 題意未明確定義時，可接受合理且明確的分析條件、門檻或代理指標。
- 程式可執行或有圖表不代表正確；需檢查資料邏輯。
- `ONLY_GENERATION=True` 時沒有 CSV、Judge token 或 Judge 判定屬正常現象。
- 不因圖表樣式或合理實作細節不同判錯。

## 寫入結果

```powershell
python -X utf8 .codex/skills/evaluate-llm-judge-run/scripts/finalize_review.py `
  <run_dir> `
  --correct 1,2,3 `
  --incorrect 4,5 `
  --finding '4=原因' `
  --finding '5=原因'
```

此命令會取代 run 內 `summary.txt` 的 `人工複核結果` 區塊，並在 run 的父資料夾建立 `<run_name>.md`。題號必須完整、互斥且排序；每題錯誤都要提供原因。
