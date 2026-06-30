"""向量存储 — ChromaDB 后端，支持多 Collection."""

import os
import uuid
from typing import Optional


class VectorStore:
    """ChromaDB 向量存储。支持多 Collection（冷热分离）。"""

    def __init__(self, persist_dir: str = "data/vector_store",
                 collection_name: str = "kb_static"):
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        self._client: Optional["chromadb.PersistentClient"] = None

    @property
    def client(self):
        if self._client is None:
            import chromadb
            os.makedirs(self.persist_dir, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=self.persist_dir,
                settings=chromadb.config.Settings(anonymized_telemetry=False),
            )
        return self._client

    def get_collection(self, name: str = None):
        """获取或创建 collection。"""
        return self.client.get_or_create_collection(
            name=name or self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(self, chunks: list[dict],
                   embeddings: list[list[float]],
                   collection: str = None) -> int:
        """追加块到指定 collection（增量，不清除已有数据）。"""
        if not chunks:
            return 0

        coll = self.get_collection(collection or self.collection_name)
        ids = [str(uuid.uuid4()) for _ in chunks]
        texts = [c["text"] for c in chunks]
        metadatas = [c["metadata"] for c in chunks]

        batch_size = 500
        for i in range(0, len(chunks), batch_size):
            end = min(i + batch_size, len(chunks))
            coll.add(
                ids=ids[i:end],
                embeddings=embeddings[i:end],
                documents=texts[i:end],
                metadatas=metadatas[i:end],
            )
        return len(chunks)

    def search(self, query_embedding: list[float],
               top_k: int = 10,
               collection: str = None,
               where: Optional[dict] = None) -> list[dict]:
        """语义搜索单个 collection。"""
        coll = self.get_collection(collection or self.collection_name)
        results = coll.query(
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
                "score": 1.0 - results["distances"][0][i],
            })
        return items

    def count(self, collection: str = None) -> int:
        try:
            return self.get_collection(collection or self.collection_name).count()
        except Exception:
            return 0

    def list_collections(self) -> list[str]:
        return [c.name for c in self.client.list_collections()]

    def clear(self, collection: str = None):
        name = collection or self.collection_name
        try:
            self.client.delete_collection(name)
        except Exception:
            pass
