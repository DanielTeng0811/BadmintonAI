# 本機 BadmintonGPT 剪輯服務

這是可選功能，使用 sibling `badminton-reels` 專案；原本未啟用時的部署、模型、資料庫預設保留。
已啟用的安裝會保存 `.runtime/badminton-gpt/local-reels.json`，後續setup/up繼續套用。
啟用會重建／重啟本機服務，現有帳號、聊天與資料volume保留。

## Commands

先確定原本的 BadmintonGPT 已完成 build／ingest，可正常啟動。reels 的 `.env` 使用其既有
OpenAI、Fish、HF金鑰，不把這些金鑰寫入Git或Docker映像。此整合需Docker運行。

```bash
cd /Users/danielteng/Code/BadmintonAI

# 啟用／更新本機剪輯服務與BadmintonGPT接線
python3 scripts/badminton_gpt.py reels-enable --reels-path /Users/danielteng/Code/badminton-reels

# 檢查服務
python3 scripts/badminton_gpt.py status

# 實際MCP建任務、無旁白合成、帳號隔離與影片Range串流；不呼叫GPT/TTS
python3 scripts/badminton_gpt.py reels-verify

# 再用目前設定的真正聊天模型測試讀技能、查片單、建立剪輯計畫；會消耗模型API
python3 scripts/badminton_gpt.py reels-verify --live

# 原預設模型無權限時，僅替這次模型測試指定可用模型，不修改部署預設
python3 scripts/badminton_gpt.py reels-verify --live --test-model gpt-5.1

# 兩個專案使用不同key時，僅在測試程序使用reels現有key，不保存或顯示key
python3 scripts/badminton_gpt.py reels-verify --live --test-model gpt-5.1 --test-reels-key

# 停用並恢復原本的無剪輯服務部署；保留影片volume
python3 scripts/badminton_gpt.py reels-disable
```

入口仍是 [本機 BadmintonGPT](http://127.0.0.1:8765)。重新整理頁面後，可在新對話嘗試：

> 幫我剪 Viktor_AXELSEN_LEE_Zii_Jia_EAST_VENTURES_Indonesia_Open_2022_Semifinals
> 裡面李梓嘉有殺球的精彩回合，保留完整回合，一邊打一邊專業解說。
> 用 shot_collection、continuous、語速1.2、fit_narration，最多3回合、180秒，不要主播。

或指定 `3_22_21`、`3_23_21` 兩個回合，使用 `rally_collection`。
未指定新模式時，MCP仍預設原版 `news_report`。style是口吻，剪輯目的與旁白方式獨立。

## 接線與權限

- 原本固定版本的submodule不變；本機薄映像套入MCP任務歸屬檢查。
- Gateway只連Docker內的 `http://badminton-reels:8900/mcp`，白名單為
  `list_matches`、`generate_reel`、`get_reel_status`、`get_reel_result`、`resume_reel`。
- skills／SOUL只在啟用後宣告這項功能，其他遠端分析服務仍未啟用。
- 使用reels自己的HF片單，不假設資料庫所有比賽都能剪片。明確要求產片的任務才授權下載。
- reels沒有發布主機port；回傳的影片URL經同來源 `/reels/files/{job_id}.mp4`，需登入並符合任務帳號。
- MCP輪詢／結果／續跑也檢查帳號；任務歸屬另存ledger，不捏造API費用。
- 影片支援HTTP Range，既有播放器可播放；其他帳號及匿名請求無法讀取。
- 外部實驗室的reels網址與部署未修改；這套接線適用本機localhost部署。

## 修改位置

| 檔案 | 用途 |
| --- | --- |
| scripts/badminton_gpt.py | reels-enable／disable／verify入口，可選Compose覆蓋 |
| scripts/badminton_gpt_reels.py | 本機服務、schema白名單、路由與技能配置 |
| scripts/local_reels_gateway.py | 建任務記錄帳號、查詢／續跑驗證帳號，保留原版其他MCP流程 |
| local_auth/reels.py / server.py | 登入與歸屬驗證後串流影片 |
| docs/badminton-reels-skill.md | 給BadmintonGPT讀取的操作說明 |
| tests/test_reels_integration.py | 可選部署、帳號歸屬、Range／cookie邊界測試 |
| scripts/test_badminton_gpt_reels_live.py | 真實服務／影片／可選模型整合測試 |

來源的剪輯邏輯與所有CLI範例在 `badminton-reels/docs/planned-reels.md`。

## 現階段限制

旁白來自逐拍標註，並未獨立看影片驗證每一句，也沒有逐拍強制聲畫對齊。
新模式保留完整HF來源片段，不保證上游剪點完整。來源無音軌時，none輸出可為靜音。
完整來源不代表原版news_report也改了剪點；原版仍維持原有聲畫配合行為。
reels尚未向gateway回報實際OpenAI／Fish費用，所以帳號使用量不包含這些外部產片費用。
不是每項選球組合都有影片；工具會明確回報無符合條件、片長不足、額度不足等錯誤。

驗證結果存於 `.runtime/badminton-gpt/reels-verification.json` 與
`.runtime/badminton-gpt/reels-agent-verification.json`；後者只有 `--live` 才產生。
HTTP驗證使用暫存登入資料庫，不修改既有使用者密碼。

2026-11-03實測：BadmintonAI現有API key未開通預設 `gpt-6-luna`，測試 `gpt-5.1` 也遭拒。
reels既有key可使用 `gpt-5.1`；只在測試程序換用這組憑證，真正AI已完成讀技能、
查片單並呼叫generate_reel。原本部署的key／模型均未修改。
MCP／合成／播放已通過。要讓網頁聊天也可用，請先在 BadmintonAI 的 `.env`
設定對目標模型有權限的 `OPENAI_API_KEY`，再由終端機暫時覆寫模型啟動：

```bash
NANOBOT_MODEL=gpt-5.1 python3 scripts/badminton_gpt.py up
```

此指令會重啟服務，`.env`中的原預設不變；未帶覆寫重新執行up會回到原設定。
`--test-model`只影響測試程序，並不會替網頁聊天切換模型。
`--test-reels-key`也只影響該測試，憑證透過stdin傳入，不寫入報告或部署設定。
