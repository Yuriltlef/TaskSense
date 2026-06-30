"""向量存储 — ChromaDB 后端."""

import os
import uuid
from typing import Optional

import chromadb
from chromadb.config import Settings as ChromaSettings


class VectorStore:
    """ChromaDB 向量存储。

    管理文档块的嵌入向量和元数据。
    """

    def __init__(self, persist_dir: str = "data/vector_store",
                 collection_name: str = "aviation_knowledge"):
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        self._client: Optional[chromadb.PersistentClient] = None
        self._collection = None

    @property
    def client(self) -> chromadb.PersistentClient:
        if self._client is None:
            os.makedirs(self.persist_dir, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=self.persist_dir,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        return self._client

    @property
    def collection(self):
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def add_chunks(self, chunks: list[dict],
                   embeddings: list[list[float]]) -> int:
        """批量添加文档块。

        Args:
            chunks: [{text, metadata}, ...]
            embeddings: 对应的嵌入向量

        Returns:
            添加的块数量
        """
        if not chunks:
            return 0

        ids = [str(uuid.uuid4()) for _ in chunks]
        texts = [c["text"] for c in chunks]
        metadatas = [c["metadata"] for c in chunks]

        # 分批添加（Chroma 有批大小限制）
        batch_size = 500
        for i in range(0, len(chunks), batch_size):
            end = min(i + batch_size, len(chunks))
            self.collection.add(
                ids=ids[i:end],
                embeddings=embeddings[i:end],
                documents=texts[i:end],
                metadatas=metadatas[i:end],
            )

        return len(chunks)

    def search(self, query_embedding: list[float],
               top_k: int = 10,
               where: Optional[dict] = None) -> list[dict]:
        """语义搜索。

        Args:
            query_embedding: 查询向量
            top_k: 返回结果数
            where: Chroma 过滤条件

        Returns:
            [{id, text, metadata, score}, ...]
        """
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        if not results["ids"] or not results["ids"][0]:
            return []

        items = []
        for i in range(len(results["ids"][0])):
            items.append({
                "id": results["ids"][0][i],
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i] or {},
                "score": 1.0 - results["distances"][0][i],  # cosine → similarity
            })
        return items

    def count(self) -> int:
        """当前存储的块数量。"""
        return self.collection.count()

    def clear(self):
        """清空存储。"""
        try:
            self.client.delete_collection(self.collection_name)
        except Exception:
            pass
        self._collection = None
