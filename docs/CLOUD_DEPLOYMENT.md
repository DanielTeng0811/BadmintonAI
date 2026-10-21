# 後續雲端部署方向

使用者已確認：BadmintonAI 後續要能部署到雲端，保留 Cloudflare Tunnel 的部署方向。本機可獨立運作是目前的開發入口，不是將產品永久限制在 localhost。此文件記錄後續設計與尚未完成的項目；目前沒有建立 tunnel、購買網域或公開任何服務。

## 上游實際採用的架構

依固定版本 `7cccbb18aba8bcfa096f22b923fb2aa16326e6ed` 的 [上游部署文件](../vendor/badmintonGPT/docs/DEPLOY.md) 與 [Compose](../vendor/badmintonGPT/docker-compose.yml)：

```text
瀏覽器 → 公開網域 / Cloudflare Access → Cloudflare Tunnel
       → 主機上的 cloudflared → gateway → badminton-db
                                      → 遠端影片／分析服務
```

Cloudflare 提供公開入口與身分驗證；nanobot、WebUI、工具執行及 SQLite 在可執行 Docker 的來源主機上。這份部署不是把整個應用程式放進 Cloudflare Workers 或 Pages。

上游 README 公布 `badmintongpt.nycu-adsl.cc`，但這個網域及部署設定不能證明來源主機的位置。固定版本的部署文件沒有明確指出學校機房、校內實驗室主機或特定雲端供應商。實際位置需向上游維運者確認，不能從 Cloudflare 入口推定。

## 本專案保留的上線路線

```text
瀏覽器 → 自有 HTTPS 網域 → Cloudflare Tunnel
       → cloudflared → auth:8080 → gateway:8765 → badminton-db:8801
```

- 雲端 VM 或有使用權限且可長期運作的實驗室主機執行 Docker Compose，保存帳號、對話及研究資料。
- 公開 tunnel 指向 `auth:8080`，不能沿用上游的 `gateway:8765` 入口而繞過本專案登入。
- 保留現在的帳號、密碼與帳號識別方式；只加入 Tunnel 不需要遷移使用者或對話。
- Cloudflare Access 可額外限制外部訪客，並非本專案帳號系統的必要依賴。若之後要以 Access / Google 登入取代密碼，需另外實作經驗證的身分映射與帳號綁定；不直接把外部 email 當作既有 `username@local.badminton`，避免對話擁有權失配。
- gateway 與資料庫維持內部服務，不作為公開 tunnel 路由。
- Luna API key 與影片服務設定保留，這次不新增金鑰、存取權或影片依賴。

## 上線時需要準備

| 資源 | 用途 |
| --- | --- |
| 一台可持續運作、有持久磁碟且能執行 Docker 的主機 | 真正執行應用程式；可在雲端或校內 |
| 自己可管理的 Cloudflare 帳號與網站 zone | 管理正式 tunnel 與 DNS |
| 可管理 DNS 的網域／子網域 | 提供固定 HTTPS 網址；已有可用網域不必另外購買 |
| 該 tunnel 的 connector token | 供主機上的 cloudflared 連接；不提交到 Git |
| 可用的模型 API key | 啟用 Luna 回答；與網站公開、登入功能分開處理 |

依 [Cloudflare Tunnel 說明](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/)，connector 從來源主機主動建立向外連線，不必為網站開放來源主機的入站連接埠；仍須允許 tunnel 所需的對外網路連線。固定公開網域的操作見 [官方建立 tunnel 文件](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel/)。

## 接公開網域前要完成的實作與驗收

目前 `local_auth/server.py` 明確只允許本機 Host，且來源檢查使用本機 HTTP scheme，因此**現在不能只把 tunnel 接上就宣稱正式上線完成**。到部署階段需完成：

1. 設定明確的公開 origin 與 Host 允許清單，讓 HTTPS 下的表單、API 與 WebSocket 通過同來源檢查；不任意信任使用者傳入的 forwarded headers。
2. 正式 HTTPS 模式使用 Secure cookie，保留 HttpOnly、SameSite、登出撤銷及 session 隔離。
3. 由受信任的 tunnel 取得訪客 IP，驗證登入頻率限制不會把所有外部訪客誤視為同一來源，也不能被偽造 header 繞過。
4. 在公開入口前完成首次管理員設定，確認註冊開放範圍及是否額外啟用 Access。
5. 搬移並共同備份 `auth_state`、`badminton_state` 與資料庫；保留帳號與對話擁有權。從單一持久化主機起步，不直接讓多個應用副本各自寫入不同 SQLite。
6. 經正式網址重新驗證登入／登出、跨帳號對話與附件隔離、WebSocket、重啟保留資料及備份還原。付費模型與影片另在權限到位後驗證。

上述尚未實作或進行公開環境測試；現有本機驗證結果不代替正式網域的驗收。
