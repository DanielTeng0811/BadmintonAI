"""
LLM 處理模組 - 負責語言模型的載入和推論
"""

import json
import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    pipeline
)
from config import (
    LLM_MODEL_NAME,
    MAX_NEW_TOKENS,
    DO_SAMPLE,
    COLUMN_DEFINITION_FILE
)


class LLMHandler:
    """處理 LLM 相關的所有操作"""

    def __init__(self, model_name=LLM_MODEL_NAME):
        """
        初始化 LLM

        Args:
            model_name: 模型名稱
        """
        self.model_name = model_name
        self.llm_pipe = None
        self.column_info_text = None

    def setup(self):
        """設定並載入語言模型"""
        # 設定量化參數，減少記憶體使用
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16
        )

        # 檢查 GPU
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"使用裝置: {device}")

        # 載入語言模型
        llm = AutoModelForCausalLM.from_pretrained(
            pretrained_model_name_or_path=self.model_name,
            quantization_config=bnb_config,
            torch_dtype=torch.bfloat16,
            device_map="auto",
            low_cpu_mem_usage=True,
        )

        # 載入 tokenizer
        tokenizer = AutoTokenizer.from_pretrained(self.model_name)

        # 使用 pipeline 包裝模型推論介面
        self.llm_pipe = pipeline(
            "text-generation",
            model=llm,
            tokenizer=tokenizer,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=DO_SAMPLE,
            temperature=None,
            top_p=None,
            top_k=None,
            device_map="auto",
        )

        # 載入欄位定義
        self.column_info_text = self._load_column_definitions()

        print("✅ LLM 載入完成")

    def _load_column_definitions(self):
        """載入欄位定義"""
        with open(COLUMN_DEFINITION_FILE, "r", encoding="utf-8") as f:
            full_definitions = json.load(f)

        column_definitions = full_definitions.get("data_columns", [])

        if isinstance(column_definitions, list) and all(
            isinstance(item, dict) and 'column' in item and 'definition' in item
            for item in column_definitions
        ):
            column_info_text = "\n".join(
                [f"- {item['column']}: {item['definition']}" for item in column_definitions]
            )
        else:
            column_info_text = "錯誤：'data_columns' 的格式不符合預期。"

        return column_info_text

    def generate_sql(self, query: str) -> str:
        """
        使用 LLM 生成 SQL 查詢

        Args:
            query: 使用者的自然語言查詢

        Returns:
            LLM 生成的 SQL 或回應
        """
        system_prompt = f"""
You are an expert in badminton sports and data analysis.
Below are the column names and their definitions for the data table. Please refer to these definitions when answering questions:

{self.column_info_text}

If the question cannot be answered using a single simple SELECT statement,
respond exactly with: "I can not help you." Otherwise, please write SQL code for the user to query in SQLite, avoiding instructions unrelated to the question.
**important** Only provide SQL code
""".strip()

        user_prompt = f"### Question: \n{query}"

        chats = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        response = self.llm_pipe(chats)[0]['generated_text'][-1]['content'].strip()
        return response

    def test_generation(self, prompt="介紹羽球"):
        """測試 LLM 生成功能"""
        if self.llm_pipe is None:
            print("❌ 請先執行 setup() 載入模型")
            return

        outputs = self.llm_pipe(prompt)
        print(outputs[0]["generated_text"])


if __name__ == "__main__":
    # 測試功能
    handler = LLMHandler()
    handler.setup()
    handler.test_generation()
