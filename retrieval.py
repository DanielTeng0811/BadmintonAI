"""
檢索模組 - 負責 BM25、Embedding 和 RAG 檢索
"""

import json
import jieba
import numpy as np
from typing import List, Tuple
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer
from config import (
    QUERY_TEMPLATES_FILE,
    EMBEDDING_MODEL_NAME,
    SIMILARITY_THRESHOLD,
    RRF_K
)


class RetrievalSystem:
    """檢索系統 - 整合 BM25 和 Embedding 檢索"""

    def __init__(self, embedding_model_name=EMBEDDING_MODEL_NAME):
        """
        初始化檢索系統

        Args:
            embedding_model_name: Embedding 模型名稱
        """
        self.embedding_model_name = embedding_model_name
        self.chunks = []
        self.sql_templates = []
        self.bm25 = None
        self.embedding_model = None
        self.chunks_embeddings = None

    def setup(self):
        """設定檢索系統"""
        # 載入查詢模板
        self._load_query_templates()

        # 建立 BM25 模型
        self._setup_bm25()

        # 建立 Embedding 模型
        self._setup_embedding()

        print("✅ 檢索系統初始化完成")

    def _load_query_templates(self):
        """載入查詢模板"""
        with open(QUERY_TEMPLATES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.chunks = [item["question"] for item in data]
        self.sql_templates = [item["sql_template"] for item in data]

        print(f"✅ 載入了 {len(self.chunks)} 個查詢模板")

    def _setup_bm25(self):
        """建立 BM25 檢索模型"""
        tokenized_chunks = [list(jieba.cut(chunk)) for chunk in self.chunks]
        self.bm25 = BM25Okapi(tokenized_chunks)
        print("✅ BM25 模型建立完成")

    def _setup_embedding(self):
        """建立向量檢索模型"""
        self.embedding_model = SentenceTransformer(self.embedding_model_name)
        self.chunks_embeddings = self.embedding_model.encode(
            self.chunks,
            show_progress_bar=True
        )
        print("✅ Embedding 模型建立完成")

    def bm25_retrieve(self, query: str) -> List[str]:
        """
        BM25 檢索

        Args:
            query: 查詢字串

        Returns:
            排序後的文檔列表
        """
        tokenized_query = list(jieba.cut(query))
        scores = self.bm25.get_scores(tokenized_query)
        rank = sorted(zip(self.chunks, scores), key=lambda x: x[1], reverse=True)
        return [chunk for chunk, _ in rank]

    def embedding_retrieve(self, query: str) -> List[str]:
        """
        向量檢索

        Args:
            query: 查詢字串

        Returns:
            排序後的文檔列表
        """
        query_embedding = self.embedding_model.encode(query)
        # 計算餘弦相似度
        scores = np.dot(self.chunks_embeddings, query_embedding) / (
            np.linalg.norm(self.chunks_embeddings, axis=1) * np.linalg.norm(query_embedding)
        )
        rank = sorted(zip(self.chunks, scores), key=lambda x: x[1], reverse=True)
        return [chunk for chunk, _ in rank]

    def reciprocal_rank_fusion(self, *ranked_lists, k=RRF_K) -> List[str]:
        """
        融合多個檢索結果

        Args:
            ranked_lists: 多個排序後的列表
            k: RRF 參數

        Returns:
            融合後的排序列表
        """
        scores = {}
        for rl in ranked_lists:
            for rank, doc in enumerate(rl, start=1):
                scores[doc] = scores.get(doc, 0.0) + 1.0 / (k + rank)
        fused = sorted(scores.items(), key=lambda x: -x[1])
        return [doc for doc, _ in fused]

    def calculate_similarity(self, query: str, chunk: str) -> float:
        """
        計算查詢和文檔的相似度

        Args:
            query: 查詢字串
            chunk: 文檔字串

        Returns:
            相似度分數
        """
        chunk_idx = self.chunks.index(chunk)
        query_embedding = self.embedding_model.encode(query)
        similarity = np.dot(self.chunks_embeddings[chunk_idx], query_embedding) / (
            np.linalg.norm(self.chunks_embeddings[chunk_idx]) * np.linalg.norm(query_embedding)
        )
        return float(similarity)

    def retrieve(self, query: str, threshold=SIMILARITY_THRESHOLD) -> Tuple[str, float, bool]:
        """
        執行完整的檢索流程

        Args:
            query: 查詢字串
            threshold: 相似度閾值

        Returns:
            (最佳匹配的 SQL 模板或空字串, 相似度分數, 是否匹配成功)
        """
        # BM25 檢索
        bm25_ranked = self.bm25_retrieve(query)

        # Embedding 檢索
        embedding_ranked = self.embedding_retrieve(query)

        # 融合結果
        fused_ranked = self.reciprocal_rank_fusion(bm25_ranked, embedding_ranked)

        # 取得最佳匹配
        top1 = fused_ranked[0]
        top1_idx = self.chunks.index(top1)

        # 計算相似度
        similarity_score = self.calculate_similarity(query, top1)

        print(f"Top 1 similar: {top1}")
        print(f"相似度分數: {similarity_score:.4f}")

        # 判斷是否匹配
        if similarity_score >= threshold:
            return self.sql_templates[top1_idx], similarity_score, True
        else:
            return "", similarity_score, False


if __name__ == "__main__":
    # 測試功能
    retrieval = RetrievalSystem()
    retrieval.setup()

    test_query = "這位選手大多站在哪裡發球？"
    sql_template, score, matched = retrieval.retrieve(test_query)

    if matched:
        print(f"\n✅ 匹配成功！")
        print(f"SQL Template: {sql_template}")
    else:
        print(f"\n❌ 無法匹配，需要使用 LLM 生成")
