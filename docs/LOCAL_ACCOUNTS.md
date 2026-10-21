# 本機帳號與對話隔離

本機版使用自己的登入服務，不需要 Cloudflare Access、實驗室帳號、郵件寄送或外部登入供應商。Luna API key、進階分析及影片服務仍保留原有待設定狀態；帳號功能本身不呼叫模型。

## 第一次使用

```bash
python3 scripts/badminton_gpt.py build
python3 scripts/badminton_gpt.py up
```

開啟 <http://127.0.0.1:8765>，會顯示「建立管理員帳號」。管理員名稱固定為 `admin`，由你設定至少 12 個字元的密碼並確認。沒有預設密碼，也沒有預先建立的共用帳號。

建立後進入聊天介面。側欄顯示目前帳號，提供本機帳號設定及登出入口。帳號設定頁是 <http://127.0.0.1:8765/auth/account>。

其他使用者在登入頁選擇「還沒有帳號？建立帳號」，即可建立一般帳號。帳號需為 3–32 個字元，以小寫英文字母開頭，可包含數字、底線或連字號；不需要填寫真實電子郵件。一般帳號無法存取全域模型設定或帳號管理功能。

## 管理與密碼

- 所有使用者可在本機帳號頁變更自己的密碼；需提供目前密碼並確認新密碼，更新後原有登入全部失效。
- 管理員可在帳號頁查看帳號清單、停用或重新啟用一般使用者。停用會撤銷登入並關閉既有聊天連線。
- 登出後登入 cookie 失效，已取得的聊天 API token 不能用來繞過登入；其他開啟中的分頁也會重載登入狀態。
- 唯一管理員不能從網頁停用自己。管理員權限不代表可以讀取其他使用者的對話。

若忘記密碼，具有此電腦 Docker 操作權限的人可在終端機互動式重設，不必刪除帳號或對話：

```bash
docker compose --env-file .env -f compose.badminton-gpt.yml exec auth python3 -m local_auth.manage reset-password admin
```

密碼以隱藏輸入方式輸入，不要放入命令列參數。列出帳號可用相同指令末端的 `python3 -m local_auth.manage list`。

## 隔離的範圍

| 項目 | 行為 |
| --- | --- |
| 對話清單、訊息及 UI transcript | 僅擁有者可讀取 |
| 刪除、附加及發送至既有對話 | 伺服器檢查擁有者，不能只改 chat ID 繞過 |
| WebSocket 訂閱 | 不允許訂閱其他使用者的對話 |
| 側欄標題、釘選、封存資訊 | 各帳號分開保存 |
| 專案目錄 | 使用 nanobot 既有的帳號專屬根目錄與 restricted 存取模式 |
| 附件網址 | 簽章依帳號區分，取得他人的網址仍不能讀取 |
| 模型的共享歷史記憶 | 維持關閉，避免其他對話被放入 prompt |
| 舊版匿名驗證預覽 | 歸屬 admin，不公開給新使用者 |
| 羽球資料庫與應用程式規則 | 共用研究資料，與私人對話分開 |

伺服器端會覆寫用戶端自帶的身分 header；聊天 API 與 WebSocket 的 bootstrap token 也會綁定帳號。即使知道另一個帳號的 chat ID、token 或附件網址，也不能直接取用。

這是單機多使用者版本。入口只綁定 `127.0.0.1`，沒有公開部署；本機作業系統／Docker 管理者仍可直接存取磁碟與容器，不屬於應用程式帳號隔離的邊界。

## 儲存與部署

後續已保留「雲端／校內主機 + Cloudflare Tunnel」的上線方向，詳見 [雲端部署規劃](CLOUD_DEPLOYMENT.md)。公開入口將接到本帳號服務，沿用既有使用者與對話；目前尚未啟用正式網域或 HTTPS 模式。

新增 `auth` 容器接收本機 8765 的請求，登入成功後才轉送給內部 `gateway`。gateway 的 8765 不再直接公開到主機，避免繞過登入入口。SQLite 資料庫 MCP 維持原先設定及共用唯讀資料。

- `auth_state` volume：本機帳號、加鹽 scrypt 密碼雜湊、登入 session 雜湊與 token 綁定。
- `badminton_state` volume：nanobot 對話、帳號擁有權及各帳號側欄資料。
- `down` 不刪除以上 volume；`up`、重新建置及重新啟動保留帳號與對話。
- 這兩個 volume 都應保留，備份時須一起處理，避免帳號和對話擁有權失配。

登入使用 HttpOnly、SameSite=Strict cookie。所有變更帳號的請求需通過同來源檢查，登入嘗試有頻率限制，session 有效期為七天。此入口為 HTTP loopback；沒有假裝已完成網際網路 HTTPS 部署。

## 驗證

```bash
# 不呼叫模型；使用一次性帳號資料庫連到真實 nanobot。
python3 scripts/badminton_gpt.py verify-auth

# 原有資料、MCP、Python 與圖表接線檢查。
python3 scripts/badminton_gpt.py verify

# 目前主線回歸測試；先依 README 安裝 requirements-dev.txt。
python -m pytest -q --disable-warnings
```

`verify-auth` 使用獨立臨時 auth DB，不建立正式管理員密碼、不動正式帳號資料庫。測試會建立兩個一般帳號，透過真實 HTTP／WebSocket 驗證清單、讀取、刪除、偽造身分、token、附件、側欄、專案根目錄、登出、停用及密碼更新。只使用內建 `/help` 指令及標明為測試資料的附件，不需要有效 API key。

每次報告保存在 `.runtime/badminton-gpt/auth-verification/` 的獨立檔案中。驗證結果與限制見 [帳號驗證基準](../benchmarks/badminton_gpt/auth_baseline.json)。這些檢查驗證帳號與資料存取，不代表 Luna 回答或影片服務已實測。

## 程式位置

- `local_auth/`：本機登入服務、密碼／session 儲存、帳號頁及 Dockerfile。
- `scripts/badminton_gpt_account_overlay.py`：對固定上游 build copy 套用帳號按鈕、登出行為、附件簽章隔離等調整；不修改上游 submodule。
- `scripts/test_badminton_gpt_auth_live.py`：實際多帳號驗證。
- `tests/test_local_accounts.py`：帳號建立、雜湊、撤銷、持久化、頻率限制與 proxy 邊界測試。

實作使用 [Python scrypt](https://docs.python.org/3/library/hashlib.html#hashlib.scrypt) 與 [aiohttp HTTP／WebSocket](https://docs.aiohttp.org/en/stable/web_reference.html)，沒有外部登入依賴。
