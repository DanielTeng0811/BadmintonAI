# 舊版 BadmintonAI 研究存檔

這裡保留原本的 Streamlit 應用、多模型實驗、LLM-as-a-Judge、評測結果與歷史部署設定。主線入口已移至根目錄的 [BadmintonGPT](../README.md)，不會載入這裡的程式。

本次整理保留研究結果的內容與相對目錄；舊報告、notebook 和 manifest 中的原始路徑未重寫。`data/` 仍在 repository 根目錄供新舊版本共用，來源資料未搬移或修改。帳號資料與現有 Docker volumes 也未搬動。

## 路徑對照

| 原位置 | 現位置 |
| --- | --- |
| `front_page.py`、`config/`、`utils/` | `legacy/` 下同名路徑 |
| `LLM_as_a_Judge/`（包含結果、notebook 與圖表） | `legacy/LLM_as_a_Judge/` |
| `evaluation/` | `legacy/evaluation/` |
| 舊版 `tests/` 與 fixtures | `legacy/tests/`；目前主線測試仍在根目錄 `tests/` |
| Streamlit／Hugging Face 部署與研究文件 | `legacy/docs/` |
| `Dockerfile`、`.streamlit/`、`.devcontainer/`、`packages.txt` | `legacy/` 下同名路徑 |
| 舊版套件與 pytest 設定 | `legacy/requirements*.txt`、`legacy/pytest.ini` |
| LLM run 複核 skill | `legacy/.codex/skills/evaluate-llm-judge-run/` |

整理前完整版本仍可從 Git commit `2f8bee6` 取得。歷史文件描述當時的路徑與平台，不能直接當作目前主線的部署指令。

## 離線回歸測試

從 repository 根目錄執行，另用舊版專屬 Python 環境：

```bash
python3 -m venv .venv-legacy
source .venv-legacy/bin/activate
python -m pip install -r legacy/requirements-dev.txt
python -m pytest -c legacy/pytest.ini legacy/tests
```

這套離線測試使用假的模型 client；執行正式評測程式則可能呼叫付費模型。

## 手動啟動舊版

在上面的舊版環境中執行：

```bash
cd legacy
streamlit run front_page.py
```

沿用原本的 `APP_PASSWORD` 與模型設定；由 repository 根目錄的 `.env` 提供，或以環境變數設定。舊版評測也讀取根目錄 `.env`，不複製金鑰到存檔目錄。評測程式與使用方式見 [LLM-as-a-Judge 導覽](LLM_as_a_Judge/README.md)。

如需建置存檔的 Streamlit image，Docker build context 必須是 repository 根目錄：

```bash
docker build -f legacy/Dockerfile -t badmintonai-streamlit:legacy .
```

根目錄已移除舊版 Hugging Face README metadata 與自動 Streamlit 入口；目前新系統使用 Compose。舊平台重新發布需另行設定，不能把此 image 當作新的 BadmintonGPT。
