# 使用與開發環境相容、仍受支援的 Python 版本
FROM python:3.11-slim

# 安裝系統依賴 (包含中文字體 fonts-wqy-zenhei)
RUN apt-get update && apt-get install -y \
    fonts-wqy-zenhei \
    && rm -rf /var/lib/apt/lists/*

# Hugging Face Docker Spaces 以 UID 1000 執行容器。
RUN useradd --create-home --uid 1000 user
WORKDIR /home/user/app

# 先安裝依賴，讓後續程式碼變更能使用 Docker layer cache。
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# App runtime 只需要 UI、核心模組、資料與 Streamlit 設定；
# 評測輸出、測試與本機開發檔案不應進入部署 image。
COPY --chown=user:user front_page.py ./
COPY --chown=user:user config ./config
COPY --chown=user:user utils ./utils
COPY --chown=user:user data ./data
COPY --chown=user:user .streamlit ./.streamlit

RUN mkdir -p logs data/processed && chown -R user:user /home/user/app
USER user
ENV HOME=/home/user \
    STREAMLIT_SERVER_PORT=7860 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0

# 開放 Hugging Face Spaces 預設的 7860 Port
EXPOSE 7860

# 啟動 Streamlit
CMD ["streamlit", "run", "front_page.py"]
