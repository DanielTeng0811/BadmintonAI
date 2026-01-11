# 使用 Python 3.9 作為基底映像檔
FROM python:3.9-slim

# 設定工作目錄
# 設定工作目錄
WORKDIR /app

# 安裝系統依賴 (包含中文字體 fonts-wqy-zenhei)
RUN apt-get update && apt-get install -y \
    fonts-wqy-zenhei \
    && rm -rf /var/lib/apt/lists/*

# 複製 requirements.txt 並安裝套件
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製所有程式碼到工作目錄
COPY . .

# 開放 Hugging Face Spaces 預設的 7860 Port
EXPOSE 7860

# 強制設定 Streamlit Port 為 7860
ENV STREAMLIT_SERVER_PORT=7860
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0

# 啟動 Streamlit
CMD ["streamlit", "run", "front_page.py"]
