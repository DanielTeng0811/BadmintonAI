# 部署到 Hugging Face Spaces

本專案以 Docker Space 部署。Space 會依根目錄 `README.md` 的 YAML 設定與 `Dockerfile` 建置，並在 port `7860` 提供 Streamlit App。

## 建立自己的 Space

1. 登入 Hugging Face，開啟 [Spaces](https://huggingface.co/spaces)，點選 **Create new Space**。
2. 選擇自己的帳號或組織、填入名稱，例如 `badminton-ai`。
3. SDK 選擇 **Docker**，硬體先選 `CPU Basic`。
4. 可見性建議選 **Private**；只有需要公開展示時才選 Public。
5. 建立完成後，複製該 Space 的 Git URL。

## 推送 `develop`

在本專案根目錄執行；將 `<HF_USER>` 與 `<SPACE_NAME>` 改成自己的值：

```bash
git remote add huggingface https://huggingface.co/spaces/<HF_USER>/<SPACE_NAME>
git push huggingface develop:main
```

第一次推送後，Hugging Face 會自動開始建置 Docker image。之後每次要更新 Space，只要再推送目前的 `develop`：

```bash
git push huggingface develop:main
```

## 設定 Secrets

在 Space 的 **Settings → Variables and secrets** 新增下列 Secret。不要把任何 key 寫進 Git、README 或 Dockerfile。

| Secret | 必要性 | 說明 |
| --- | --- | --- |
| `APP_PASSWORD` | 必要 | App 登入密碼；未設定時 App 會拒絕啟動。 |
| `OPENAI_API_KEY` | 視使用模型 | OpenAI API key。 |
| `ANTHROPIC_API_KEY` | 視使用模型 | Claude API key。 |
| `GEMINI_API_KEY` | 視使用模型 | Gemini API key。 |

Secrets 會在 Docker Space 的執行期以環境變數提供，因此現有的 `os.getenv()` 讀取方式可直接使用。

## 資料保存限制

Space 重新啟動、休眠或重建後，容器內的可寫入資料可能遺失。因此使用者上傳的 CSV 與產生的 `data/processed/` 檔案只適合暫時分析，不適合長期保存。

- 要保留正式資料：將原始 CSV 與處理後資料存回自己管理的 Git repo、雲端硬碟或資料庫。
- 要做長期多人上傳：後續應改用外部儲存，例如 Cloud Storage 或資料庫。

## 部署後檢查

1. 等待 Space 顯示 **Running**。
2. 開啟 App，確認可以以 `APP_PASSWORD` 登入。
3. 選擇一個已設定 key 的模型供應商，送出小型分析問題。
4. 確認圖表、下載按鈕與 token 計數正常。
