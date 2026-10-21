# 專案結構與維護規則

目前主線為 [BadmintonGPT 重現](BADMINTON_GPT_REPRODUCTION.md)。唯一服務入口是 `scripts/badminton_gpt.py` 與 `compose.badminton-gpt.yml`；舊版集中於 [legacy/](../legacy/README.md)。

## 目錄責任

| 路徑 | 用途與維護原則 |
| --- | --- |
| `local_auth/` | 帳號、密碼與 session；登入後代理 HTTP／WebSocket 至內部 gateway |
| `scripts/badminton_gpt.py` | 統一管理建置、匯入、啟動與驗證 |
| `scripts/badminton_gpt_account_overlay.py` | 對建置副本套用帳號、登出與附件隔離調整 |
| `scripts/import_shuttleset_data.py` | 目前資料去重、來源追溯、歷史資料對應 |
| `scripts/create_shuttleset_benchmark.py` | 獨立 CSV oracle 與凍結答案 |
| `scripts/import_badminton_gpt_data.py` | 保留舊資料轉換，支援歷史表與回歸測試 |
| `data/sources/` | 原始 ShuttleSet ZIP；不執行裡面的程式碼，不修改來源 |
| `vendor/badmintonGPT/` | 固定版本上游 submodule；本地修改透過 overlay，不直接更動上游 |
| `data/` | 新舊版本共用的研究資料；保留來源名稱與內容以維持可追溯性 |
| `benchmarks/badminton_gpt/` | 自有題目、來源 hash、凍結答案及驗證基準 |
| `tests/` | 目前主線的帳號、資料轉換與 benchmark 測試 |
| `docs/` | 目前系統的重現、帳號、部署與維護文件 |
| `legacy/` | 舊版 Streamlit、模型比較、LLM-as-a-Judge、研究結果、測試與歷史部署設定 |
| `.runtime/badminton-gpt/` | 可重建的建置副本、轉換資料與測試報告；不納入版本控制 |

根目錄 `requirements.txt` 僅提供本機帳號服務的 Python 依賴，`requirements-dev.txt` 加入目前主線測試工具。Agent／WebUI／MCP 依賴由 Docker images 安裝。舊版套件清單留在 `legacy/requirements*.txt`。

## 資料與研究紀錄

- 不更動既有 `data/` 的來源內容；新增轉換產物應另存，並記錄來源 hash。
- 完成的歷史 run 保留在 `legacy/LLM_as_a_Judge/result_<model>/<run_name>/`，不要為整理目錄重寫 notebook、圖表、摘要或 manifest 中的歷史路徑。
- 本機未追蹤的歷史 `eval_results/` 仍忽略於 Git；不要把私人評測輸出意外提交。
- 本次整理只搬移歷史結果，舊報告中的原始路徑可依 [路徑對照](../legacy/README.md) 找到。
- 現有 `auth_state` 與 `badminton_state` volumes 需共同備份，不以清理 repository 為由刪除。

## 驗證與發布

目前主線執行 `python -m pytest`。涉及服務接線時，再執行 `python3 scripts/badminton_gpt.py verify` 與 `verify-auth`。模型 benchmark 需明確使用 `--live`，且等待有效金鑰到位。

修改舊版或搬移其路徑時，另在舊版環境執行 `python -m pytest -c legacy/pytest.ini legacy/tests`；不要為執行主線測試而強制安裝全部歷史模型與繪圖套件。

`main` 保存已驗證的版本；新工作使用 `codex/<工作名稱>` 分支。推送前確認沒有提交 `.env`、本機帳號、session、Docker volumes 或 `.runtime/`。雲端上線條件見 [部署規劃](CLOUD_DEPLOYMENT.md)。
