# 🚀 BadmintonAI - Streamlit Cloud 部署指南

本指南將協助您將 BadmintonAI 應用程式部署到 Streamlit Cloud。

---

## 📋 部署前檢查清單

在部署前，請確認以下事項：

### ✅ 1. 確認 Git Repository 乾淨
```bash
# 檢查是否有敏感資料被 commit
git log --all --full-history -- .env
git log --all --full-history -- .streamlit/secrets.toml

# 若發現敏感資料已被 commit，請參考「清除 Git 歷史」章節
```

### ✅ 2. 確認 .gitignore 設定正確
確認以下檔案已被排除：
- `.env`
- `.streamlit/secrets.toml`
- `*.log`
- `llm_debug_log.txt`

### ✅ 3. 準備 API Keys
您需要準備以下 API Keys（至少一個）：
- **OpenAI API Key**: 從 [OpenAI Platform](https://platform.openai.com/api-keys) 取得
- **Gemini API Key**: 從 [Google AI Studio](https://aistudio.google.com/app/apikey) 取得

---

## 🛠️ 部署步驟

### Step 1: 推送程式碼到 GitHub

```bash
# 1. 初始化 Git (如果尚未初始化)
git init

# 2. 加入所有檔案 (敏感檔案會被 .gitignore 排除)
git add .

# 3. 建立 commit
git commit -m "Prepare for Streamlit Cloud deployment"

# 4. 建立 GitHub Repository 並推送
git remote add origin https://github.com/你的帳號/BadmintonAI.git
git branch -M main
git push -u origin main
```

### Step 2: 連接 Streamlit Cloud

1. 前往 [Streamlit Cloud](https://share.streamlit.io/)
2. 使用 GitHub 帳號登入
3. 點擊 **"New app"**

### Step 3: 配置應用程式

在 Streamlit Cloud 建立應用程式介面：

| 欄位 | 設定值 |
|------|--------|
| **Repository** | `你的帳號/BadmintonAI` |
| **Branch** | `main` |
| **Main file path** | `front_page.py` |
| **App URL** (optional) | 自訂網址 (如 `badminton-ai`) |

### Step 4: 設定 Secrets (API Keys)

1. 在應用程式設定頁面，找到 **"Advanced settings"** → **"Secrets"**
2. 貼上以下內容（替換為您的實際 API Key）：

```toml
# OpenAI API Key (必填，若使用 OpenAI)
OPENAI_API_KEY = "sk-your-actual-openai-api-key-here"

# Gemini API Key (選填，若使用 Gemini)
GEMINI_API_KEY = "your-actual-gemini-api-key-here"
```

3. 點擊 **"Save"**

### Step 5: 部署應用程式

1. 點擊 **"Deploy!"** 按鈕
2. 等待 2-5 分鐘，Streamlit Cloud 會自動：
   - 安裝 `requirements.txt` 中的相依套件
   - 啟動應用程式
   - 提供公開網址

---

## ⚙️ 進階設定

### 自訂 Python 版本 (可選)

建立 `.python-version` 檔案指定 Python 版本：

```bash
echo "3.11" > .python-version
git add .python-version
git commit -m "Add Python version specification"
git push
```

### 增加記憶體限制 (可選)

若遇到記憶體不足問題，可在 Streamlit Cloud 的 **Settings** → **Resources** 調整：
- **Free tier**: 最多 1GB RAM
- **付費方案**: 可升級至更大記憶體

---

## 🐛 常見問題排解

### 問題 1: 應用程式啟動失敗，顯示 "ModuleNotFoundError"

**原因**: `requirements.txt` 缺少必要套件

**解決方法**:
```bash
# 確認所有相依套件都列在 requirements.txt
pip freeze > requirements.txt

# 提交並推送
git add requirements.txt
git commit -m "Update dependencies"
git push
```

### 問題 2: 應用程式啟動後顯示 "⚠️ 請輸入 API Key"

**原因**: Secrets 未正確設定

**解決方法**:
1. 前往 Streamlit Cloud → 你的應用程式 → **Settings** → **Secrets**
2. 確認 `OPENAI_API_KEY` 或 `GEMINI_API_KEY` 已正確填入
3. 點擊 **"Save"** 並重新啟動應用程式

### 問題 3: 應用程式顯示 "PermissionError: [Errno 13] Permission denied"

**原因**: 嘗試寫入檔案系統 (Streamlit Cloud 為 read-only)

**解決方法**:
本專案已修正此問題，將 log 改為儲存在 `st.session_state` 而非磁碟檔案。若仍遇到此問題，請檢查是否有其他程式碼嘗試寫入檔案。

### 問題 4: 資料檔案 (CSV/DB) 找不到

**原因**: 資料檔案被 `.gitignore` 排除，未上傳到 GitHub

**解決方法**:
```bash
# 確認資料檔案未被 .gitignore 排除
# 編輯 .gitignore，確認以下行被註解掉：
# #*.csv  (已註解，CSV 會被上傳)

# 加入資料檔案並推送
git add all_dataset.csv processed_new_3.csv processed_new_3.db court_place.txt
git commit -m "Add data files for deployment"
git push
```

**注意**: 若資料檔案過大 (>100MB)，需使用 **Git LFS** 或外部儲存服務。

---

## 🔐 安全性建議

### 1. 絕不將 API Keys commit 到 Git

```bash
# 檢查是否意外 commit 了敏感資料
git log --all --oneline | grep -i "api\|key\|secret"

# 若發現敏感資料，立即撤銷並重設 API Key
```

### 2. 定期輪換 API Keys

建議每 3-6 個月更換一次 API Keys，並更新 Streamlit Secrets。

### 3. 限制 API Key 權限

- **OpenAI**: 設定 usage limits 避免意外超額
- **Gemini**: 使用 API Key restrictions 限制來源 IP

---

## 📊 監控與維護

### 查看應用程式 Logs

1. 前往 Streamlit Cloud → 你的應用程式
2. 點擊右上角的 **三點選單** → **Logs**
3. 查看即時錯誤訊息與執行狀態

### 重新部署

當您推送新的 commit 到 GitHub 時，Streamlit Cloud 會**自動重新部署**。

手動重新啟動：
1. 前往應用程式頁面
2. 點擊 **三點選單** → **Reboot app**

---

## 🎯 成功部署檢查

部署成功後，您應該能夠：

✅ 訪問公開網址 (如 `https://你的帳號-badminton-ai-xxx.streamlit.app`)
✅ 在側邊欄選擇 API 模式 (Gemini / OpenAI)
✅ 輸入問題並看到 AI 生成的分析圖表
✅ 上傳新資料並自動處理
✅ 下載分析報告 (ZIP)

---

## 🆘 需要協助？

若遇到其他問題，請參考：

- [Streamlit Cloud 官方文件](https://docs.streamlit.io/streamlit-community-cloud)
- [Streamlit Community Forum](https://discuss.streamlit.io/)
- [本專案 GitHub Issues](https://github.com/你的帳號/BadmintonAI/issues)

---

**祝您部署順利！** 🎉
