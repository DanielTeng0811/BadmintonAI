"""
主程式 - 羽球數據分析與查詢系統
整合資料庫、檢索和 LLM 功能
"""

from database import csv_to_sqlite, execute_query
from llm_handler import LLMHandler
from retrieval import RetrievalSystem


class BadmintonQuerySystem:
    """羽球查詢系統主類別"""

    def __init__(self):
        """初始化系統"""
        self.llm_handler = LLMHandler()
        self.retrieval_system = RetrievalSystem()

    def setup(self, load_llm=True):
        """
        設定系統

        Args:
            load_llm: 是否載入 LLM（載入需要較長時間和記憶體）
        """
        print("=== 初始化羽球查詢系統 ===\n")

        print("Step 1: 設定檢索系統...")
        self.retrieval_system.setup()

        if load_llm:
            print("\nStep 2: 載入 LLM（這可能需要幾分鐘）...")
            self.llm_handler.setup()
        else:
            print("\nStep 2: 跳過 LLM 載入（僅使用模板匹配）")

        print("\n✅ 系統初始化完成！\n")

    def query(self, user_query: str) -> str:
        """
        處理使用者查詢

        Args:
            user_query: 使用者的自然語言查詢

        Returns:
            SQL 查詢語句
        """
        print(f"\n📝 使用者查詢: {user_query}\n")

        # 使用檢索系統尋找匹配的模板
        sql_template, similarity_score, matched = self.retrieval_system.retrieve(user_query)

        if matched:
            print(f"✅ 匹配到預設模板")
            print(f"SQL: {sql_template}")
            return sql_template
        else:
            print(f"⚠️ 無匹配模板（相似度: {similarity_score:.4f} < 閾值）")

            if self.llm_handler.llm_pipe is not None:
                print("🤖 使用 LLM 生成 SQL...\n")
                sql_response = self.llm_handler.generate_sql(user_query)
                print(f"🧩 LLM 輸出：\n{sql_response}")
                return sql_response
            else:
                print("❌ LLM 未載入，無法生成 SQL")
                return ""

    def execute_and_display(self, sql_query: str):
        """
        執行 SQL 並顯示結果

        Args:
            sql_query: SQL 查詢語句
        """
        try:
            results = execute_query(sql_query)
            print(f"\n📊 查詢結果（共 {len(results)} 筆）：")
            for i, row in enumerate(results, 1):
                print(f"{i}. {row}")
        except Exception as e:
            print(f"\n❌ 執行 SQL 時發生錯誤: {e}")

    def interactive_mode(self):
        """互動式查詢模式"""
        print("=" * 60)
        print("🏸 羽球數據查詢系統 - 互動模式")
        print("=" * 60)
        print("輸入您的查詢問題，或輸入 'quit' 離開\n")

        while True:
            try:
                user_input = input("🔍 您的問題: ").strip()

                if not user_input:
                    continue

                if user_input.lower() in ['quit', 'exit', 'q']:
                    print("\n👋 感謝使用，再見！")
                    break

                # 處理查詢
                sql_query = self.query(user_input)

                # 詢問是否執行
                if sql_query and "SELECT" in sql_query.upper():
                    execute = input("\n執行此 SQL 查詢？(y/n): ").strip().lower()
                    if execute == 'y':
                        self.execute_and_display(sql_query)

                print("\n" + "-" * 60 + "\n")

            except KeyboardInterrupt:
                print("\n\n👋 感謝使用，再見！")
                break
            except Exception as e:
                print(f"\n❌ 發生錯誤: {e}\n")


def main():
    """主程式入口"""
    # 選擇是否轉換 CSV（如果已經轉換過可以註解掉）
    print("=== 資料庫準備 ===")
    convert_csv = input("是否需要將 CSV 轉換為 SQLite？(y/n): ").strip().lower()
    if convert_csv == 'y':
        csv_to_sqlite()
    print()

    # 選擇是否載入 LLM
    load_llm = input("是否載入 LLM？（需要較長時間和 GPU/記憶體）(y/n): ").strip().lower()
    load_llm = (load_llm == 'y')

    # 初始化系統
    system = BadmintonQuerySystem()
    system.setup(load_llm=load_llm)

    # 進入互動模式
    system.interactive_mode()


if __name__ == "__main__":
    main()
