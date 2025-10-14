"""
配置檔案 - 所有常數和設定
"""

# 資料庫設定
CSV_FILE = "all_dataset.csv"
DB_FILE = "data.db"
TABLE_NAME = "badminton_data"

# JSON 檔案路徑
QUERY_TEMPLATES_FILE = "badminton_query_templates.json"
COLUMN_DEFINITION_FILE = "column_definition.json"

# 模型設定
LLM_MODEL_NAME = "unsloth/gemma-3-4b-it"
EMBEDDING_MODEL_NAME = "intfloat/multilingual-e5-large"

# LLM 參數
MAX_NEW_TOKENS = 512
DO_SAMPLE = False

# 檢索參數
SIMILARITY_THRESHOLD = 0.95
RRF_K = 60
