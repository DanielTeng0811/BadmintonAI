def create_judge_prompt(question: str, code: str, column_definitions_info: str, reference_code: str) -> str:
    """
    建立給 AI 裁判的 prompt，用於對照標準答案，進行二元判定程式碼是否正確
    """
    return f"""
    你是一位嚴格且專業的羽球數據分析專家與資深 Python 工程師。
    你的任務是檢查一段 Pandas 分析程式碼是否正確。
    我們已經有一份「標準答案 (Reference Code)」，你必須對照標準答案，來判定生成的程式碼是否正確。

    [重要前提]
    1. 評估的 AI 已經內建了專案特定的資料欄位定義 (Schema)。
    2. 請關注「資料處理邏輯」與「欄位選用」是否與標準答案一致或等價。如果寫法不同但邏輯等價（例如篩選條件的寫法不同但效果相同），應視為正確。

    [欄位定義參考]
    {column_definitions_info}

    [使用者問題]
    {question}

    [標準答案 (Reference Code)]
    ```python
{reference_code}
    ```

    [生成的程式碼]
    ```python
{code}
    ```

    [評分任務]
    請對照標準答案，判定生成的程式碼是否正確 (true/false)。
    只要核心過濾邏輯、欄位選用、以及計算方式與標準答案邏輯等價，就判定為 true。
    如果有嚴重的數據污染、欄位誤用、或是核心計算錯誤，請判定為 false。

    [回傳格式 (JSON ONLY)]
    請務必回傳純 JSON 格式。
    格式如下：
    {{
        "code_correct": true,
        "reasoning": "詳細解釋為何判定為正確或錯誤。若為錯誤，請具體指出哪裡與標準答案的邏輯不同。"
    }}
    """
